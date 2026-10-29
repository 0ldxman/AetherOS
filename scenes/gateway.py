"""Сцены экрана входа: игрок подключается к удалённой машине.

Это сцены консоли (scenes/engine.py), а не страница: Python собирает их, браузер
проигрывает (static/ui/console.js, desktop/static/boot/lock.js).

Aether это связь на радиоволнах, а у ПК игрока радио нет. Поэтому сначала ПК выходит
через обычный интернет на МОСТ (остаток общей сети, у него есть радиооборудование), а
мост уже ведёт радиосвязь до узла. Первый этап честно говорит на сетевом языке (tcp,
tls), дальше только радио. Между этапами смена режима (чёрный кадр), а шапка (клиент,
имя узла, через какой мост, chassis) печатается заново:

    1/9 bridge        ПК без радио, каталог мостов (ближние и дальние, рабочие и нет),
                      выбор ближайшего рабочего, правка Zero видна как след: ключ клиента
                      внесён в белый список «3 min ago by ██████»
    2/9 tune          радио моста, антенна, заземление, поиск несущей, захват частоты узла
    3/9 path          станции на пути сигнала (часть молчит: сеть местами разрушена)
    4/9 sync          преамбула, кадры, модуляция, коррекция ошибок, скорость канала
    5/9 key exchange  пара ключей, отпечатки, полоса «deriving key», ключи сессии
    6/9 identity      цепочка сертификатов (издатель замазан, срок давно вышел),
                      статус отзыва недоступен, ключ узла с картинкой отпечатка,
                      вопрос про неизвестный узел (на знакомом узле его нет)
    7/9 node          chassis, система, владелец замазан, центр не отвечает, политика
    8/9 access        баннер, методы входа (два из трёх недоступны), выбор: Discord, а
                      на месте второго варианта кто-то печатает фразу от первого лица
    9/9 session       если игрок пошёл за этой фразой: имя узла в шапке портится
                      (aether-main -> aether-null, меняются только main/null),
                      chassis остаётся прежним, потом открывается сессия «witness»

После входа узел здоровается, как сервер на Linux: логотип, «System information»
(нагрузка, радио, хранилище, часы работы), уведомления узла, последний вход и почта.
В этом приветствии спрятаны следы мира (центр молчит, журнал копится, чей-то последний
вход перед тишиной). См. _motd.

Если игрок долго ничего не выбирает, фраза стирается и набирается другая.

Объём: на первом заходе текста много (шум: параметры линии, станции, расширения
сертификата, политика), на знакомом узле (known=True) шум пропускается. После каждого
этапа экран держится столько, чтобы его успели прочитать (read()).

Организацию-владельца здесь НЕ указываем: поле owner и издатель сертификата замазаны,
игрок должен сам догадаться, чья это машина. Сцена целиком видна в исходнике страницы.
Даты (игровая, последний контакт с центром) берутся из machines/world/dates.py.
"""
import hashlib

from scenes.engine import Option, Scene
from machines.world.identity import CORE_HOST
from machines.world.dates import days_since, world

STAGES = 9

CLIENT = "AETHER LINK 3.2"
PROTOCOL = "alp/3.2"
NULL_HOST = "aether-null"
EXTERNAL = "DISCORD"
CIPHER = "x25519 / chacha20-poly1305 / sha256"
KEY_ID = "9c1e 44a0 b73d 08f2 e5a1 63cc"
CLIENT_KEY = "SHA256:Qm7cRk0VnT2yJfX4uL8aZpE3wH1dBs9oGcNx6tYvAeI"   # если ключ посетителя не передан
BRIDGE = "narthex"
BRIDGE_NOTE = "for the one who comes to see"
OWNER_MASK = 14
SYSTEM = "AETHER 9.1 (halcyon)"
KERNEL = "aek 5.8.14-hal"

BANNER = (
    "Authorized personnel only.",
    "All access is monitored and logged.",
    "Recorded sessions may be disclosed to the owner of this system.",
    "Unauthorized access is an offence and will be pursued.",
    "By continuing you accept these terms.",
    "",
    "Connection details are retained for audit.",
    "Report faults to the node operator.",
)

# Станции на пути сигнала: (название, пеленг °, расстояние км, уровень dBm; None: нет ответа).
# Одна станция молчит, сигнал идёт в обход через соседнюю (сеть местами разрушена).
ROUTE = (
    ("VX-04", 42, 312, -81),
    ("VX-11", 57, 488, -86),
    ("VX-19", 61, 602, None),
    ("VX-19", 61, 602, None),
    ("gw-██", 63, 655, -97),
    ("aether-main", 66, 701, -92),
)
# Каталог мостов: (имя, расстояние км, состояние, подробности). Ближайшие часто мертвы;
# клиент берёт ближайший рабочий. Имена: греческие ветры и вестники (эфир, воздух).
BRIDGES = (
    ("zephyr", 12, "offline", "no carrier"),
    ("boreas", 38, "no answer", "silent for 1,204 d"),
    (BRIDGE, 91, "reachable", "rtt 38 ms"),
    ("notos", 214, "degraded", "rtt 410 ms, loss 12 %"),
    ("euros", 388, "offline", "no carrier"),
    ("iris", 530, "reachable", "rtt 96 ms"),
    ("hermes", 702, "offline", "no carrier"),
)
BRIDGE_STYLES = {"offline": "error", "no answer": "warning", "degraded": "warning", "reachable": "success"}

# Фразы незнакомца, от первого лица. Первая выбирается случайно при каждом заходе,
# а если игрок молчит, текст стирается и набирается одна из следующих.
VOICE = (
    "i left it open for you",
    "come in. i'll keep it open",
    "i can let you in. quietly.",
    "you don't have to ask them",
    "this way. they aren't looking at this door",
    "i opened this for you. hurry",
)
VOICE_AGAIN = (
    "...still here",
    "i can't hold this open for long",
    "are you there?",
    "i left it open for you",
)
VOICE_AFTER_MS = 2200                  # через сколько после появления входа начинает печатать
VOICE_AGAIN_MS = (20000, 30000)        # через сколько молчания перепечатывает


LOGO = tuple(r"""
    _    _____ _____ _   _ _____ ____  
   / \  | ____|_   _| | | | ____|  _ \ 
  / _ \ |  _|   | | | |_| |  _| | |_) |
 / ___ \| |___  | | |  _  | |___|  _ < 
/_/   \_\_____| |_| |_| |_|_____|_| \_\
""".strip("\n").split("\n"))
LAST_LOGIN = "2027-10-29 23:41 UTC"     # последний вход на узел перед тем, как центр замолчал


# ---------- общие куски ----------

def _header(s, ident, *, host=None, chassis=None, saved=False, via=True):
    """Шапка этапа: клиент, узел, мост и (с этапа 6) chassis. Имя узла с id для glitch."""
    s.say(CLIENT, (f"  ·  {PROTOCOL}", "dim"))
    if saved:
        s.row("target", ident.hostname, note="(saved)")
    else:
        s.row("node", host or ident.hostname, id="host")
    if via:
        s.row("via", BRIDGE, "dim")
    if chassis:
        s.row("chassis", chassis, "dim")


def _stage(s, number, title):
    s.blank()
    s.say(f"-- {number}/{STAGES}  {title} --", style="dim")


def _next_screen(s):
    """Конец этапа: экран держится столько, чтобы его прочитали, потом смена режима."""
    s.read().cut()


def _route(s):
    """Станции на пути. Молчащая станция вызывается второй раз, потом идёт обход."""
    seen = set()
    for index, (name, bearing, km, level) in enumerate(ROUTE):
        retry = name in seen
        seen.add(name)
        delay = km / 300     # свет проходит 300 км за миллисекунду
        s.wait((250, 700))
        head = "stations  " if index == 0 else " " * 10
        what = f"{name:<12}{bearing:03d}°  {km:>4} km  {delay:.2f} ms  "
        if level is None:
            s.say(head, what, ("no answer", "warning"), ("  (retry)" if retry else "", "dim"))
        else:
            s.say(head, what, (f"{level} dBm", "dim"), ("  (detour)" if name == "gw-██" else "", "dim"))


def _scan_range(freq):
    """Диапазон поиска вокруг частоты узла: «14.000-14.500»."""
    try:
        low = int(float(freq) * 2) / 2
    except ValueError:
        return str(freq)                     # адрес задан не частотой: вокруг него нечего искать
    return f"{low:.3f}-{low + 0.5:.3f}"


def _options(*, late):
    """Discord и фраза незнакомца. late: фраза появляется сама, а не сразу."""
    return [
        Option("discord", "d", "external authority", tag=EXTERNAL),
        Option(
            "bypass", "?", VOICE, also=("/",), style="warning",
            appear=VOICE_AFTER_MS if late else None,
            retype=VOICE_AGAIN if late else (),
            retype_after=VOICE_AGAIN_MS,
        ),
    ]


# ---------- этапы ----------
# known: узел игрок уже видел. Шум (необязательные подробности) тогда пропускается.

def _bridge(s, ident, known, client_key):
    _header(s, ident, saved=True, via=False)
    _stage(s, 1, "bridge")
    s.row("client", "x86_64  ·  radio: no device found", "warning")
    if not known:
        s.row("client key", client_key, "dim", width=11)
    s.say(
        f"directory {len(BRIDGES)} bridges, last sync {world().beacon_last_sync} ({days_since(world().beacon_last_sync)} d ago)",
        style="warning",
    )
    if known:
        s.task(f"select    {BRIDGE} ", "reachable", ms=(300, 700), style="success")
    else:
        s.say("bridges   nearest first", style="dim")
        for name, km, status, detail in BRIDGES:
            s.wait((200, 600))
            s.say(
                "          ", f"{name:<9}{km:>4} km  ",
                (f"{status:<10}", BRIDGE_STYLES[status]), (detail, "dim"),
                ("   <" if name == BRIDGE else "", "success"),
            )
        s.say(f"select    {BRIDGE}  (nearest reachable)")
    s.task(f"connect   {BRIDGE}  tcp 443 ", "established", ms=(450, 1000), style="success")
    if not known:
        s.task("tls       1.3 handshake ", "ok", ms=(350, 800), style="success")
    s.row("bridge", f"{BRIDGE}  ·  rf0 wideband 2-30 MHz  ·  loop 40 m  ·  earth 2.8 ohm", "dim")
    if not known:
        s.row("operator", f'note: "{BRIDGE_NOTE}"', "dim")
    s.task("auth      client key ", "allowlisted", ms=(500, 1100), style="success")
    s.say("          allowlist: 1 entry (this client)", style="dim")
    s.say("          added 3 min ago by " + Scene.mask(10) + "  [restricted]", style="warning")
    s.row("tunnel", "alp over tls  ·  frame 1380", "dim")
    s.row("channel", "7 of 16 allocated  ·  tx 40 W", "dim")
    s.say("          handing the link to the radio")


def _tune(s, ident, known, client_key):
    _header(s, ident, saved=True)
    _stage(s, 2, "tune")
    s.row("radio", "rf0  aether wideband 2-30 MHz", "dim")
    if not known:
        s.row("antenna", "loop 40 m  ·  vswr 1.3", "dim")
        s.task("earth     electrode 2.8 ohm ", "ok", style="success", ms=(300, 700))
    s.task(f"beacons   {ident.hostname} ", f"{ident.address} MHz", style="dim", ms=(350, 800))
    s.say(
        f"          cached entry, last sync {world().beacon_last_sync} ({days_since(world().beacon_last_sync)} d ago)",
        style="warning",
    )
    s.task(f"scan      {_scan_range(ident.address)} MHz ", "3 carriers", style="dim", ms=(900, 1600))
    s.task(f"carrier   {ident.address} MHz ", "locked", ms=(500, 1000), style="success")
    s.row("noise", "-112 dBm  ·  snr 31 dB", "dim")
    if not known:
        s.row("mode", "ground wave + skywave", "dim")


def _path(s, ident, known, client_key):
    _header(s, ident)
    _stage(s, 3, "path")
    s.say(f"stations  directory {world().stations_known}, reachable {world().stations_reachable}", style="dim")
    s.say("path      probing stations (max 12 hops)")
    _route(s)
    if not known:
        s.row("route", "6 stations, 1 silent, 1 detour, loss 0.4 %", "dim")
        s.task("loss      computing ", "118 dB", style="dim", ms=(300, 700))
        s.task("ground    coupling ", "ok", style="success", ms=(300, 700))
    s.row("delay", "2.33 ms  (min 2.29, max 2.41)", "dim")
    s.task("frame     measuring max size ", "1452 bytes", style="dim", ms=(400, 900))


def _sync(s, ident, known, client_key):
    _header(s, ident)
    _stage(s, 4, "sync")
    s.task("preamble  detecting ", "found", ms=(300, 700), style="success")
    s.task("frame     synchronising ", "locked", ms=(500, 1100), style="success")
    s.burst(
        ("offer     ", PROTOCOL + " alp/3.1 alp/3.0"),
        ("accept    ", PROTOCOL),
    )
    s.row("modem", "ofdm 1024 carriers  qpsk / 16qam adaptive", "dim")
    s.row("fec", "ldpc 3/4  ber 2e-6", "dim")
    if not known:
        s.row("doppler", "+0.4 Hz  ·  multipath 3 paths", "dim")
        s.burst(
            ("server    ", "banner alp-3.2 build 2020.09.2"),
            ("feature   ", "multiplex     on"),
            ("feature   ", "resume        on"),
            ("feature   ", "padding       on"),
            ("feature   ", "compression   off"),
        )
        s.row("arq", "retransmits 0.8 %", "dim")
    s.row("protocol", PROTOCOL)
    s.row("rate", "38 Mbit/s  (adaptive)")
    s.task("link      measuring quality ", "good", ms=(300, 700), style="success")


def _key_exchange(s, ident, known, client_key):
    _header(s, ident)
    _stage(s, 5, "key exchange")
    s.row("kex", "x25519  ·  kdf hkdf-sha256", "dim")
    s.row("cipher", CIPHER, "dim")
    s.task("client    generating key pair ", "OK", ms=(500, 900))
    if not known:
        s.row("client", f"ed25519  {client_key}", "dim")
    s.task("node      sending challenge ", "OK", ms=(700, 1300))
    if not known:
        s.burst(
            ("send      ", ("32 bytes  client ephemeral key", "dim")),
            ("recv      ", ("32 bytes  node ephemeral key", "dim")),
            ("verify    ", ("signature ok", "dim")),
        )
    s.row("key id", KEY_ID, "dim")
    s.bar("session   deriving key ", ms=(1400, 2100))
    if not known:
        s.burst(
            ("keys      ", ("tx ready", "dim")),
            ("keys      ", ("rx ready", "dim")),
            ("rekey     ", ("every 1 h / 1 GiB", "dim")),
        )
    s.task("session   key accepted ", "OK", ms=(300, 600))


def _identity(s, ident, known, client_key):
    _header(s, ident)
    _stage(s, 6, "identity")
    s.say("certificate chain  (2)")
    mask = Scene.mask(OWNER_MASK)
    s.burst(
        ("  [0] subject   ", ident.hostname),
        ("      issuer    ", (mask, None), ("  [restricted]", "dim")),
        ("      serial    ", ("0x4f21a7c93b05", "dim")),
        ("      names     ", (ident.hostname, "dim")),
        ("      usage     ", ("session, key agreement", "dim")),
        ("      algorithm ", ("ed25519 / sha256", "dim")),
        ("      valid     ", ("2019-11-02 .. " + str(world().cert_not_after), "dim"),
         (f"  expired {days_since(world().cert_not_after)} d ago", "warning")),
        ("  [1] subject   ", (mask, None)),
        ("      usage     ", ("certificate signing", "dim")),
        ("      algorithm ", ("ed25519 / sha256", "dim")),
        ("      path len  ", ("0", "dim")),
        ("      valid     ", ("2018-05-14 .. 2023-05-14", "dim")),
    )
    s.task("chain     verifying signatures ", "OK", ms=(500, 1000))
    s.task("expiry    node policy accepts expired ", "yes", style="warning", ms=(300, 700))
    s.task("revoked   checking status ", "unknown", style="warning", ms=(700, 1400))
    s.say(f"          status server {CORE_HOST} unreachable", style="dim")
    s.row("host key", f"ed25519  {ident.host_key}", "dim", width=10)
    s.blank()
    if known:
        s.say("Host key matches contacts entry.", style="dim")
        return
    s.burst(*[[("  " + line, "dim")] for line in ident.randomart], gap=(15, 60))
    s.blank()
    s.say("Node unrecognised. No prior contact on record.")
    s.wait((400, 700))
    s.say("Trust this node and continue? [y/n] ", end=False, cursor=True)
    s.wait((600, 1700))
    s.type("y", human=True)       # игрок «набрал» сам
    s.say("Node added to contacts.", style="dim")


def _node(s, ident, known, client_key):
    _header(s, ident, chassis=ident.hid)
    _stage(s, 7, "node")
    s.row("system", SYSTEM)
    s.row("kernel", KERNEL, "dim")
    if not known:
        s.row("build", "forge-03  2020-09-02", "dim")
    s.row("serial", ident.serial, "dim")
    s.row("owner", Scene.mask(OWNER_MASK), note="[restricted]")
    s.row("accounts", Scene.mask(4) + " registered", "dim")
    s.row("date", f"{world().game_date}  03:12 UTC  (beacon)", "dim")
    if not known:
        s.row("timezone", "UTC  ·  locale en_US.UTF-8", "dim")
        s.row("features", "shell, files, relay, sessions", "dim")
    s.task(f"uplink    {CORE_HOST} ", "unreachable", style="warning", ms=(900, 1800))
    s.row("contact", f"last {world().core_last_contact}  ({days_since(world().core_last_contact)} d ago)", "warning")
    s.row("reset", "3 min ago  ·  remote request", "dim")
    if not known:
        s.row("policy", "audit full  ·  recording on  ·  default deny", "dim")
    s.row("sessions", "0 active", "dim")


def _access(s, ident, known, client_key):
    _header(s, ident, chassis=ident.hid)
    _stage(s, 8, "access")
    s.blank()
    s.say("-- node banner --", style="dim")
    for row in (BANNER if not known else BANNER[:2]):
        s.say(row, style="dim")
    s.blank()
    if not known:
        s.row("policy", "lockout 3 attempts / 5 min  ·  audit full", "dim")
        s.row("limits", "1 session per client  ·  idle timeout 15 min", "dim")
        s.row("record", "session recording is on", "dim")
    s.say("auth      offered by node: external, key, password", style="dim")
    s.row("method", "key", note="no client key, skipped")
    s.row("method", "password", note="disabled by policy, skipped")
    s.row("method", "external", note="available")


def _metric(ident, key, low, high):
    """Показатель узла: число от low до high, у одного узла всегда одно и то же."""
    value = int.from_bytes(hashlib.sha256((ident.hid + "/" + key).encode()).digest()[:4], "big")
    return low + value % (high - low + 1)


def _pair(label, value, other_label="", other_value="", *, width=17, gap=24):
    """Строка в две колонки, как в приветствии сервера: «Link load  7 %      Sessions  1»."""
    left = f"{label:<{width}}{value}"
    if not other_label:
        return left
    return f"{left:<{width + gap}}{other_label:<14}{other_value}"


def _mail_line(s, mail):
    """Строка про почту: сколько непрочитанных и от кого последнее (из базы)."""
    unread = (mail or {}).get("unread", 0)
    if not unread:
        s.say("  intercom: ", ("no new messages", "dim"))
        return
    noun = "message" if unread == 1 else "messages"
    sender = mail["sender"]
    s.say(
        "  intercom: ", (f"{unread} unread {noun}", "warning"),
        (f"  (latest from {sender}, {mail['ago']} ago)" if sender else f"  (latest {mail['ago']} ago)", "dim"),
    )


def _motd(s, ident, login, mail=None, *, short=False, read=True):
    """Приветствие узла после входа: большое, с информацией и следами мира."""
    days_core = days_since(world().core_last_contact)
    events = (world().game_date - world().core_last_contact).days * world().audit_per_day + _metric(ident, "events", 0, 99)
    s.blank()
    if not short:
        for line in LOGO:
            s.say(line)
        s.blank()
    s.say(f" Welcome to {SYSTEM}  {KERNEL}  [via {BRIDGE}]")
    s.blank()
    s.say(f"  System information as of {world().game_date} 03:14 UTC", style="dim")
    s.blank()
    s.say("  " + _pair("Link load:", f"{_metric(ident, 'load', 3, 19)} %", "Sessions:", "1  (you)"))
    s.say("  " + _pair("Radio:", f"rf0 {ident.address} MHz locked", "Stations:", f"{world().stations_reachable} of {world().stations_known}"))
    s.say("  " + _pair("Vault usage:", f"{_metric(ident, 'vault', 31, 58)} % of 4 TB", "Memory:", f"{_metric(ident, 'mem', 14, 37)} % of 64 GiB"))
    s.say("  " + _pair("Processes:", f"{_metric(ident, 'proc', 180, 260)}", "Temperature:", f"{_metric(ident, 'temp', 36, 47)} C"))
    s.say("  " + _pair("Uptime:", "3 min", "Core:", "unreachable"))
    s.blank()
    if not short:
        s.say("  " + _pair("Node:", ident.hostname))
        s.say("  " + _pair("Serial:", ident.serial))
        s.say("  " + _pair("Radio gear:", "rf0 wideband 2-30 MHz  ·  rf1 not present"))
        s.blank()
    s.say(f" * Standalone mode: the core has not answered for {days_core} days.")
    s.say(f" * Audit: {events:,} events buffered in the vault, none delivered.")
    s.say(f" * Directory: bridges and stations last updated {world().beacon_last_sync}.")
    s.say(" * Updates: no channel (core unreachable).")
    s.blank()
    s.say("  Last login: ", (f"{LAST_LOGIN} as ", None), (Scene.mask(6), None), "  through aether-core")
    _mail_line(s, mail)
    s.blank()
    if not short:
        s.say(f"  This node is unattended. Sessions are recorded. Logged in as {login}.", style="dim")
        s.blank()
    if read:
        s.read(per_char=5, min_ms=1500, max_ms=7500)


# ---------- сцены ----------

def intro_scene(ident, *, known=False, client_key=CLIENT_KEY):
    """Этапы 1-8: мост, радио, вход. Заканчивается выбором.

    known: узел игрок уже добавлял в контакты, вопроса про доверие нет.
    client_key: отпечаток ключа этого посетителя (на мосту он в белом списке).
    """
    s = Scene()
    for stage in (_bridge, _tune, _path, _sync, _key_exchange, _identity, _node):
        stage(s, ident, known, client_key)
        _next_screen(s)
    _access(s, ident, known, client_key)
    s.blank()
    s.choice("entry", _options(late=True))
    return s


def menu_scene():
    """Выбор снова, без сюжета (после неудачного обходного входа)."""
    return Scene().blank().choice("entry", _options(late=False))


def discord_scene():
    s = Scene().blank()
    s.say("> requesting external authority: ", (EXTERNAL, "dim"))
    s.wait(250)
    s.say("Redirecting ...")
    return s


def bypass_scene(ident, login):
    """Игрок пошёл за фразой. Имя узла в шапке портится прямо на месте, chassis остаётся.

    Сессию ещё не открыли: это делает established_scene после ответа сервера.
    """
    s = Scene()
    s.flash().wait(120)
    s.glitch("host", NULL_HOST, frames=28)   # только main -> null: «aether-» остаётся
    s.wait(1100)                             # дать увидеть, что стало
    _next_screen(s)

    _header(s, ident, host=NULL_HOST, chassis=ident.hid)
    _stage(s, 9, "session")
    s.task(f"channel   opening ({login}) ", "OPEN", style="warning", ms=(450, 900))
    return s


def established_scene(clearance, login, ident, mail=None):
    """Сервер открыл сессию: заканчиваем подключение. Играется только после успеха."""
    s = Scene()
    s.task(f"register  login {login} ", "unregistered", style="warning", ms=(400, 900))
    s.task("pty       allocating 120x32 ", "OK", ms=(250, 550))
    s.burst(
        ("env       ", ("TERM=aether-256  LANG=en_US.UTF-8", "dim")),
        ("env       ", (f"AETHER_SESSION={login}  AETHER_SCOPE={clearance['level']}", "dim")),
        ("limits    ", ("idle 15 min  ·  recording on", "dim")),
    )
    s.task("display   negotiating 1280x720 ", "OK", ms=(400, 800))
    s.task("first frame ", "OK", ms=(300, 600))
    s.say("session established.", style="success")
    s.blank()
    s.row("user", login, "dim")
    s.row("clearance", clearance["level"], "warning")
    s.say("WARNING: session is not registered on this node", style="warning")
    _motd(s, ident, login, mail)
    s.say("Loading workspace")
    return s


def error_scene(ident):
    """Обходной вход не удался: имя возвращается. {code} подставляет браузер."""
    s = Scene().blank()
    s.glitch("host", ident.hostname, frames=20)
    s.say("ERROR: access refused ({code})", style="error")
    return s


def restored_scene(ident, *, username, clearance, guest, mail=None):
    """У игрока уже есть сессия: короткое подключение и идём дальше."""
    s = Scene()
    _header(s, ident, host=NULL_HOST if guest else ident.hostname, chassis=ident.hid)
    s.blank()
    s.task("session   restoring ", "OK", ms=(350, 700))
    s.blank()
    s.row("user", username, "dim" if guest else "success")
    s.row("clearance", clearance["level"], "warning" if guest else "success")
    if guest:
        s.say("Unregistered session: not on this node's account list.", style="warning")
    _motd(s, ident, username, mail, short=True)
    s.say("Loading workspace")
    return s
