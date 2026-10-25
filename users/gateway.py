"""Сцены экрана входа: игрок подключается к удалённой машине.

Это сцены консоли (console/scene.py), а не страница: Python собирает их, браузер
проигрывает (static/ui/console.js, desktop/static/boot/lock.js).

Подключение идёт этапами, между ними экран очищается, а шапка (клиент, имя узла,
chassis) печатается заново:

    1/5 link          определение адреса, цепочка relay (один не отвечает)
    2/5 key exchange  обмен ключами, отпечаток, полоса прогресса
    3/5 node          данные узла (hid, владелец замазан), вопрос про неизвестный узел
    4/5 access        баннер и вход: Discord, а на месте второго варианта кто-то
                      печатает фразу от первого лица, и она «оформляется под кнопку»
    5/5 session       если игрок пошёл за этой фразой: имя узла в шапке портится
                      (aether-main -> aether-null, меняются только буквы main/null),
                      chassis остаётся прежним, потом открывается гостевая сессия

Если игрок долго ничего не выбирает, фраза стирается и набирается другая.

Организацию-владельца здесь НЕ указываем, а поле owner замазано: игрок должен сам
догадаться, чья это машина. Сцена целиком видна в исходнике страницы.
"""
from console.scene import Option, Scene

STAGES = 5

CLIENT = "AETHER LINK 3.2"
SYSTEM = "AETHER"
HOST = "aether-main"
NULL_HOST = "aether-null"
ADDRESS = "10.40.7.12"
EXTERNAL = "DISCORD"
CIPHER = "x25519 / chacha20"
KEY_ID = "9c1e 44a0 b73d 08f2 e5a1 63cc"
OWNER_MASK = 14

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

def _header(s, *, host=HOST, chassis=None, saved=False):
    """Шапка этапа: клиент, узел и (с этапа 3) chassis. Имя узла с id для glitch."""
    s.say(CLIENT, ("  ·  remote session client", "dim"))
    if saved:
        s.row("target", HOST, note="(saved)")
    else:
        s.row("node", host, id="host")
    if chassis:
        s.row("chassis", chassis, "dim")


def _stage(s, number, title):
    s.blank()
    s.say(f"-- {number}/{STAGES}  {title} --", style="dim")


def _next_screen(s):
    """Конец этапа: короткая пауза и чистый экран."""
    s.wait(500).clear()


def _route(s):
    for index, (name, host, latency) in enumerate(ROUTE):
        answer = ("no answer", "warning") if latency is None else (f"{latency:>3} ms", "dim")
        s.wait(450, 250)
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


# ---------- сцены ----------

def intro_scene(hid):
    """Этапы 1-4: подключение и вход. Заканчивается выбором."""
    s = Scene()

    _header(s, saved=True)
    _stage(s, 1, "link")
    s.task("resolving ", ADDRESS, style="dim", ms=700)
    _route(s)
    s.task("link      establishing ", "OK")
    _next_screen(s)

    _header(s)
    _stage(s, 2, "key exchange")
    s.row("cipher", CIPHER, "dim")
    s.task("client    generating key pair ", "OK", ms=700)
    s.task("node      requesting public key ", "OK", ms=900)
    s.row("key id", KEY_ID, "dim")
    s.bar("session   deriving key ", ms=1700)
    s.task("session   key accepted ", "OK", ms=450)
    _next_screen(s)

    _header(s)
    _stage(s, 3, "node")
    s.row("chassis", hid, "dim")
    s.row("system", SYSTEM)
    s.row("owner", Scene.mask(OWNER_MASK), note="[restricted]")
    s.blank()
    s.say("Node unrecognised. No prior contact on record.")
    s.wait(500)
    s.say("Trust node and continue? [y/n] ", end=False)
    s.wait(700, 300)
    s.type("y", human=True)       # игрок «набрал» сам
    s.say("Node added to contacts.", style="dim")
    _next_screen(s)

    _header(s, chassis=hid)
    _stage(s, 4, "access")
    s.blank()
    s.say("-- node notice --", style="dim")
    for row in NOTICE:
        s.say(row, style="dim")
    s.blank()
    s.row("access", "external authority")
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


def bypass_scene(hid):
    """Игрок пошёл за фразой. Имя узла в шапке портится прямо на месте, chassis остаётся.

    Сессию ещё не открыли: это делает established_scene после ответа сервера.
    """
    s = Scene()
    s.flash().wait(120)
    s.glitch("host", NULL_HOST, frames=28)   # только main -> null: «aether-» остаётся
    s.wait(1100)                             # дать увидеть, что стало
    _next_screen(s)

    _header(s, host=NULL_HOST, chassis=hid)
    _stage(s, 5, "session")
    s.task("access    ", "OPEN", style="warning", ms=550)
    return s


def established_scene(clearance):
    """Сервер открыл гостевую сессию: заканчиваем подключение. Играется только после успеха."""
    s = Scene()
    s.task("display   negotiating 1280x720 ", "OK")
    s.task("first frame ", "OK", ms=450)
    s.say("session established.", style="success")
    s.blank()
    s.row("user", "guest", "dim")
    s.row("clearance", f"{clearance['level']} ({clearance['label']})", "warning")
    s.say("WARNING: session is not registered on this node", style="warning")
    s.blank()
    s.say("Loading workspace")
    return s


def error_scene():
    """Обходной вход не удался: имя возвращается. {code} подставляет браузер."""
    s = Scene().blank()
    s.glitch("host", HOST, frames=20)
    s.say("ERROR: access refused ({code})", style="error")
    return s


def restored_scene(hid, *, username, clearance, guest):
    """У игрока уже есть сессия: короткое подключение и идём дальше."""
    s = Scene()
    _header(s, host=NULL_HOST if guest else HOST, chassis=hid)
    s.blank()
    s.task("session   restoring ", "OK", ms=500)
    s.blank()
    s.row("user", username, "dim" if guest else "success")
    s.row("clearance", f"{clearance['level']} ({clearance['label']})", "warning" if guest else "success")
    if guest:
        s.say("Unregistered session: not on this node's account list.", style="warning")
    s.blank()
    s.say("Loading workspace")
    return s
