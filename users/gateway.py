"""Сцены экрана входа: игрок подключается к удалённой машине.

Это сцены консоли (console/scene.py), а не страница: Python собирает их, браузер
проигрывает (static/ui/console.js, desktop/static/boot/lock.js).

Подключение это настоящая последовательность шагов клиента Aether Link (протокол
alp), только на языке Aether. Между этапами смена режима (чёрный кадр), а шапка
(клиент, имя узла, chassis) печатается заново:

    1/7 resolve       разрешение имени, маршрут, mtu (один relay не отвечает)
    2/7 transport     соединение, выбор версии протокола и шифра
    3/7 key exchange  пара ключей, отпечаток, полоса «deriving key»
    4/7 identity      цепочка сертификатов (издатель замазан), ключ узла, вопрос
                      про неизвестный узел (на знакомом узле его нет)
    5/7 node          chassis, система, владелец замазан, uplink, число сессий
    6/7 access        баннер, методы входа (два из трёх недоступны), выбор: Discord, а
                      на месте второго варианта кто-то печатает фразу от первого лица
    7/7 session       если игрок пошёл за этой фразой: имя узла в шапке портится
                      (aether-main -> aether-null, меняются только main/null),
                      chassis остаётся прежним, потом открывается гостевая сессия

Если игрок долго ничего не выбирает, фраза стирается и набирается другая.

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
HOST_KEY = "ed25519  SHA256:9c1e44a0b73d08f2e5a163cc7d20f81b"
OWNER_MASK = 14
SYSTEM = "AETHER 9.1 (halcyon)"
KERNEL = "aek 5.8.14-hal"

NOTICE = (
    "Authorized personnel only.",
    "All access is monitored and logged.",
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
    """Конец этапа: пауза, смена режима (чёрный кадр) и чистый экран."""
    s.wait((350, 650)).cut()


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

def _resolve(s, ident):
    _header(s, ident, saved=True)
    _stage(s, 1, "resolve")
    s.row("resolver", f"{RESOLVER}  ({CORE_HOST})", "dim")
    s.task(f"query     {ident.hostname} A ", ident.address, style="dim", ms=(350, 800))
    s.task(f"query     {ident.hostname} AAAA ", "no record", style="dim", ms=(250, 600))
    s.row("ttl", "300 s", "dim")
    s.say("path      probing route")
    _route(s)
    s.task("path mtu  discovering ", "1452 bytes", style="dim", ms=(400, 900))


def _transport(s, ident):
    _header(s, ident)
    _stage(s, 2, "transport")
    s.task(f"connect   {ident.address}:{PORT} ", "established", ms=(500, 1100), style="success")
    s.row("rtt", "41 ms  (min 38, max 47)", "dim")
    s.burst(
        ("offer     ", PROTOCOL + " alp/3.1 alp/3.0"),
        ("accept    ", PROTOCOL),
    )
    s.row("protocol", PROTOCOL)
    s.row("cipher", CIPHER, "dim")
    s.task("compress  negotiating ", "off", style="dim", ms=(200, 450))


def _key_exchange(s, ident):
    _header(s, ident)
    _stage(s, 3, "key exchange")
    s.task("client    generating key pair ", "OK", ms=(500, 900))
    s.task("node      requesting public key ", "OK", ms=(700, 1300))
    s.row("key id", KEY_ID, "dim")
    s.bar("session   deriving key ", ms=(1400, 2100))
    s.task("session   key accepted ", "OK", ms=(300, 600))


def _identity(s, ident, *, known):
    _header(s, ident)
    _stage(s, 4, "identity")
    s.say("certificate chain  (2)")
    s.burst(
        ("  [0] subject   ", ident.hostname),
        ("      issuer    ", (Scene.mask(OWNER_MASK), None), ("  [restricted]", "dim")),
        ("      valid     ", ("2019-11-02 .. 2021-11-02", "dim")),
        ("  [1] subject   ", (Scene.mask(OWNER_MASK), None)),
        ("      valid     ", ("2018-05-14 .. 2023-05-14", "dim")),
    )
    s.task("chain     verifying signatures ", "OK", ms=(500, 1000))
    s.row("host key", HOST_KEY, "dim", width=10)
    s.blank()
    if known:
        s.say("Host key matches contacts entry.", style="dim")
    else:
        s.say("Node unrecognised. No prior contact on record.")
        s.wait((400, 700))
        s.say("Trust this node and continue? [y/n] ", end=False, cursor=True)
        s.wait((600, 1700))
        s.type("y", human=True)       # игрок «набрал» сам
        s.say("Node added to contacts.", style="dim")


def _node(s, ident):
    _header(s, ident, chassis=ident.hid)
    _stage(s, 5, "node")
    s.row("system", SYSTEM)
    s.row("kernel", KERNEL, "dim")
    s.row("serial", ident.serial, "dim")
    s.row("owner", Scene.mask(OWNER_MASK), note="[restricted]")
    s.task(f"uplink    {CORE_HOST} ", "reachable", style="dim", ms=(400, 900))
    s.row("sessions", "0 active", "dim")


def _access(s, ident):
    _header(s, ident, chassis=ident.hid)
    _stage(s, 6, "access")
    s.blank()
    s.say("-- node banner --", style="dim")
    for row in NOTICE:
        s.say(row, style="dim")
    s.blank()
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
    for stage in (_resolve, _transport, _key_exchange):
        stage(s, ident)
        _next_screen(s)
    _identity(s, ident, known=known)
    _next_screen(s)
    _node(s, ident)
    _next_screen(s)
    _access(s, ident)
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


def bypass_scene(ident):
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
    s.task("channel   opening (guest) ", "OPEN", style="warning", ms=(450, 900))
    return s


def established_scene(clearance):
    """Сервер открыл гостевую сессию: заканчиваем подключение. Играется только после успеха."""
    s = Scene()
    s.task("pty       allocating 120x32 ", "OK", ms=(250, 550))
    s.burst(
        ("env       ", ("TERM=aether-256  LANG=en_US.UTF-8", "dim")),
        ("env       ", ("AETHER_SESSION=guest  AETHER_SCOPE=public", "dim")),
    )
    s.task("display   negotiating 1280x720 ", "OK", ms=(400, 800))
    s.task("first frame ", "OK", ms=(300, 600))
    s.say("session established.", style="success")
    s.blank()
    s.row("user", "guest", "dim")
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
