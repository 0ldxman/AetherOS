"""Сцены экрана входа: игрок подключается к удалённой машине.

Это сцены консоли (console/scene.py), а не страница: Python собирает их, браузер
проигрывает (static/ui/console.js, desktop/static/boot/lock.js).

Подключение это настоящая последовательность шагов клиента Aether Link (протокол
alp), только на языке Aether. Между этапами смена режима (чёрный кадр), а шапка
(клиент, имя узла, chassis) печатается заново:

    1/7 resolve       имя узла: серверы имён, записи A/AAAA/TXT, маршрут (один relay
                      не отвечает), mtu
    2/7 transport     соединение, окно, часы, выбор версии протокола и возможностей
    3/7 key exchange  пара ключей, отпечатки, полоса «deriving key», ключи сессии
    4/7 identity      цепочка сертификатов (издатель замазан), отзыв, ключ узла с
                      картинкой отпечатка, вопрос про неизвестный узел (на знакомом
                      узле его нет)
    5/7 node          chassis, система, владелец замазан, политика, uplink, сессии
    6/7 access        баннер, методы входа (два из трёх недоступны), выбор: Discord, а
                      на месте второго варианта кто-то печатает фразу от первого лица
    7/7 session       если игрок пошёл за этой фразой: имя узла в шапке портится
                      (aether-main -> aether-null, меняются только main/null),
                      chassis остаётся прежним, потом открывается гостевая сессия

Если игрок долго ничего не выбирает, фраза стирается и набирается другая.

Объём: на первом заходе текста много (шум: серверы имён, параметры соединения,
расширения сертификата, политика), на знакомом узле (known=True) шум пропускается.
После каждого этапа экран держится столько, чтобы его успели прочитать (read()).

Организацию-владельца здесь НЕ указываем: поле owner и издатель сертификата замазаны,
игрок должен сам догадаться, чья это машина. Сцена целиком видна в исходнике страницы.
"""
from console.scene import Option, Scene
from machines.identity import CORE_HOST

STAGES = 7

CLIENT = "AETHER LINK 3.2"
PROTOCOL = "alp/3.2"
PORT = 7443
RESOLVER = "10.40.0.2"
NULL_HOST = "aether-null"
EXTERNAL = "DISCORD"
CIPHER = "x25519 / chacha20-poly1305 / sha256"
KEY_ID = "9c1e 44a0 b73d 08f2 e5a1 63cc"
CLIENT_ADDRESS = "10.40.31.18"
CLIENT_KEY = "SHA256:Qm7cRk0VnT2yJfX4uL8aZpE3wH1dBs9oGcNx6tYvAeI"
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

# (название, имя, задержка мс; None: нет ответа)
ROUTE = (
    ("relay 01", "VX-04", 12),
    ("relay 02", "VX-11", 27),
    ("relay 03", "···", None),
    ("relay 03", "gw-██", 41),
    ("relay 04", "aether-main", 44),
)

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


# ---------- общие куски ----------

def _header(s, ident, *, host=None, chassis=None, saved=False):
    """Шапка этапа: клиент, узел и (с этапа 4) chassis. Имя узла с id для glitch."""
    s.say(CLIENT, (f"  ·  {PROTOCOL}", "dim"))
    if saved:
        s.row("target", ident.hostname, note="(saved)")
    else:
        s.row("node", host or ident.hostname, id="host")
    if chassis:
        s.row("chassis", chassis, "dim")


def _stage(s, number, title):
    s.blank()
    s.say(f"-- {number}/{STAGES}  {title} --", style="dim")


def _next_screen(s):
    """Конец этапа: экран держится столько, чтобы его прочитали, потом смена режима."""
    s.read().cut()


def _route(s):
    for index, (name, host, latency) in enumerate(ROUTE):
        answer = ("no answer", "warning") if latency is None else (f"{latency:>3} ms", "dim")
        s.wait((250, 700))
        s.say("carrier   " if index == 0 else " " * 10, f"{name:<10}{host:<14}", answer)


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

def _resolve(s, ident, known):
    _header(s, ident, saved=True)
    _stage(s, 1, "resolve")
    if not known:
        s.row("client", f"{CLIENT_ADDRESS}/16  eth0 up", "dim")
        s.row("search", "aether, aether.local", "dim")
        s.task("gateway   10.40.0.1 ", "reachable", style="dim", ms=(250, 600))
    s.row("resolver", f"{RESOLVER}  ({CORE_HOST})", "dim")
    if not known:
        s.task("resolver  10.40.0.3 ", "no answer", style="warning", ms=(900, 1500))
        s.say("resolver   secondary silent, using primary", style="dim")
        s.row("cache", "miss", "dim")
    s.task(f"query     {ident.hostname} A ", ident.address, style="dim", ms=(350, 800))
    s.task(f"query     {ident.hostname} AAAA ", "no record", style="dim", ms=(250, 600))
    s.task(f"query     {ident.hostname} TXT ", f"v=alp1 port={PORT} caps=shell,files,relay", style="dim", ms=(300, 700))
    s.row("ttl", "300 s", "dim")
    if not known:
        s.task("reverse   " + ident.address + " ", ident.hostname, style="dim", ms=(250, 600))
    s.say("path      probing route (max 12 hops)")
    _route(s)
    if not known:
        s.row("route", "5 hops, 1 retry, loss 0 %, rtt 38-47 ms", "dim")
        s.row("target", f"{ident.hostname} is the last hop", "dim")
    s.task("path mtu  discovering ", "1452 bytes", style="dim", ms=(400, 900))


def _transport(s, ident, known):
    _header(s, ident)
    _stage(s, 2, "transport")
    s.task(f"connect   {ident.address}:{PORT} ", "established", ms=(500, 1100), style="success")
    s.row("rtt", "41 ms  (min 38, max 47)", "dim")
    if not known:
        s.row("window", "64 KiB  keepalive 15 s", "dim")
        s.row("clock", "skew +0.18 s  (tolerance 5 s)", "dim")
    s.burst(
        ("offer     ", PROTOCOL + " alp/3.1 alp/3.0"),
        ("accept    ", PROTOCOL),
    )
    s.row("protocol", PROTOCOL)
    if not known:
        s.burst(
            ("server    ", "banner alp-3.2 build 2020.09.2"),
            ("ciphers   ", "x25519+chacha20-poly1305"),
            ("          ", "x25519+aes256-gcm"),
            ("          ", "p256+aes256-gcm"),
            ("feature   ", "multiplex     on"),
            ("feature   ", "resume        on"),
            ("feature   ", "padding       on"),
            ("feature   ", "compression   off"),
        )
    s.row("cipher", CIPHER, "dim")
    s.task("compress  negotiating ", "off", style="dim", ms=(200, 450))


def _key_exchange(s, ident, known):
    _header(s, ident)
    _stage(s, 3, "key exchange")
    s.row("kex", "x25519  ·  kdf hkdf-sha256", "dim")
    s.task("client    generating key pair ", "OK", ms=(500, 900))
    if not known:
        s.row("client", f"ed25519  {CLIENT_KEY}", "dim")
    s.task("node      requesting public key ", "OK", ms=(700, 1300))
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


def _identity(s, ident, known):
    _header(s, ident)
    _stage(s, 4, "identity")
    s.say("certificate chain  (2)")
    mask = Scene.mask(OWNER_MASK)
    s.burst(
        ("  [0] subject   ", ident.hostname),
        ("      issuer    ", (mask, None), ("  [restricted]", "dim")),
        ("      serial    ", ("0x4f21a7c93b05", "dim")),
        ("      names     ", (f"{ident.hostname}, {ident.address}", "dim")),
        ("      usage     ", ("session, key agreement", "dim")),
        ("      algorithm ", ("ed25519 / sha256", "dim")),
        ("      valid     ", ("2019-11-02 .. 2021-11-02", "dim")),
        ("  [1] subject   ", (mask, None)),
        ("      usage     ", ("certificate signing", "dim")),
        ("      algorithm ", ("ed25519 / sha256", "dim")),
        ("      path len  ", ("0", "dim")),
        ("      valid     ", ("2018-05-14 .. 2023-05-14", "dim")),
    )
    s.task("chain     verifying signatures ", "OK", ms=(500, 1000))
    s.task("revoked   checking status ", "good", ms=(400, 900), style="success")
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


def _node(s, ident, known):
    _header(s, ident, chassis=ident.hid)
    _stage(s, 5, "node")
    s.row("system", SYSTEM)
    s.row("kernel", KERNEL, "dim")
    if not known:
        s.row("build", "forge-03  2020-09-02", "dim")
    s.row("serial", ident.serial, "dim")
    s.row("owner", Scene.mask(OWNER_MASK), note="[restricted]")
    s.row("accounts", Scene.mask(4) + " registered", "dim")
    if not known:
        s.row("uptime", "41 d 06:12", "dim")
        s.row("timezone", "UTC  ·  locale en_US.UTF-8", "dim")
        s.row("features", "shell, files, relay, sessions", "dim")
        s.task("time      syncing with core ", "±3 ms", style="dim", ms=(300, 700))
    s.task(f"uplink    {CORE_HOST} ", "reachable", style="dim", ms=(400, 900))
    if not known:
        s.row("policy", "audit full  ·  recording on  ·  default deny", "dim")
    s.row("sessions", "0 active", "dim")


def _access(s, ident, known):
    _header(s, ident, chassis=ident.hid)
    _stage(s, 6, "access")
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


# ---------- сцены ----------

def intro_scene(ident, *, known=False):
    """Этапы 1-6: подключение и вход. Заканчивается выбором.

    known: узел игрок уже добавлял в контакты, вопроса про доверие нет.
    """
    s = Scene()
    for stage in (_resolve, _transport, _key_exchange, _identity, _node):
        stage(s, ident, known)
        _next_screen(s)
    _access(s, ident, known)
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
    _stage(s, 7, "session")
    s.task(f"channel   opening ({login}) ", "OPEN", style="warning", ms=(450, 900))
    return s


def established_scene(clearance, login):
    """Сервер открыл гостевую сессию: заканчиваем подключение. Играется только после успеха."""
    s = Scene()
    s.task(f"register  login {login} ", "unregistered", style="warning", ms=(400, 900))
    s.task("pty       allocating 120x32 ", "OK", ms=(250, 550))
    s.burst(
        ("env       ", ("TERM=aether-256  LANG=en_US.UTF-8", "dim")),
        ("env       ", (f"AETHER_SESSION={login}  AETHER_SCOPE=public", "dim")),
        ("limits    ", ("idle 15 min  ·  recording on", "dim")),
    )
    s.task("display   negotiating 1280x720 ", "OK", ms=(400, 800))
    s.task("first frame ", "OK", ms=(300, 600))
    s.say("session established.", style="success")
    s.blank()
    s.row("user", login, "dim")
    s.row("clearance", f"{clearance['level']} ({clearance['label']})", "warning")
    s.say("WARNING: session is not registered on this node", style="warning")
    s.blank()
    s.say("Loading workspace")
    return s


def error_scene(ident):
    """Обходной вход не удался: имя возвращается. {code} подставляет браузер."""
    s = Scene().blank()
    s.glitch("host", ident.hostname, frames=20)
    s.say("ERROR: access refused ({code})", style="error")
    return s


def restored_scene(ident, *, username, clearance, guest):
    """У игрока уже есть сессия: короткое подключение и идём дальше."""
    s = Scene()
    _header(s, ident, host=NULL_HOST if guest else ident.hostname, chassis=ident.hid)
    s.blank()
    s.task("session   restoring ", "OK", ms=(350, 700))
    s.blank()
    s.row("user", username, "dim" if guest else "success")
    s.row("clearance", f"{clearance['level']} ({clearance['label']})", "warning" if guest else "success")
    if guest:
        s.say("Unregistered session: not on this node's account list.", style="warning")
    s.blank()
    s.say("Loading workspace")
    return s
