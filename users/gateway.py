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

ПРОТОТИП: данные в GATEWAY потом должны задаваться из админки (у каждой машины
свои). Организацию-владельца здесь НЕ указываем, а поле owner замазано: игрок
должен сам догадаться, чья это машина. Сцена целиком видна в исходнике страницы.
"""
from console.scene import Option, Scene

STAGES = 5

GATEWAY = {
    "client": "AETHER LINK 3.2",
    "system": "AETHER",
    "host": "aether-main",
    "null_host": "aether-null",
    "address": "10.40.7.12",
    # (название, имя, задержка мс; None: нет ответа)
    "route": [
        ("relay 01", "VX-04", 12),
        ("relay 02", "VX-11", 27),
        ("relay 03", "···", None),
        ("relay 03", "gw-██", 41),
        ("relay 04", "aether-main", 44),
    ],
    "key_exchange": {
        "cipher": "x25519 / chacha20",
        "key_id": "9c1e 44a0 b73d 08f2 e5a1 63cc",
    },
    "notice": [
        "Authorized personnel only.",
        "All access is monitored and logged.",
    ],
    "owner_mask": 14,
    "external": "DISCORD",
    # Фраза незнакомца: на месте второго варианта, от первого лица, случайная при каждом заходе
    "voice": {
        "after_ms": 2200,   # через сколько после появления входа начинает печатать
        "lines": [
            "i left it open for you",
            "come in. i'll keep it open",
            "i can let you in. quietly.",
            "you don't have to ask them",
            "this way. they aren't looking at this door",
            "i opened this for you. hurry",
        ],
        # если игрок ничего не делает, спустя это время текст стирается и набирается другой
        "again_after_ms": [20000, 30000],
        "again_lines": [
            "...still here",
            "i can't hold this open for long",
            "are you there?",
            "i left it open for you",
        ],
    },
}


# ---------- общие куски ----------

def _header(s, cfg, *, target=False, host=None, chassis=None):
    """Шапка этапа: клиент, узел и (с этапа 3) chassis. Имя узла с id для glitch."""
    s.line((cfg["client"], None), ("  ·  remote session client", "dim"))
    if target:
        s.kv("target", cfg["host"], note="(saved)")
    else:
        s.kv("node", host or cfg["host"], id="host")
    if chassis:
        s.kv("chassis", chassis, "dim")


def _stage(s, number, title):
    s.newline()
    s.line(f"-- {number}/{STAGES}  {title} --", style="dim")


def _next_screen(s):
    """Конец этапа: короткая пауза и чистый экран."""
    s.pause(500)
    s.clear()


def _discord_option(cfg):
    return Option("discord", "[ D ]", "external authority", tag=cfg["external"], keys=("d",))


def _voice_option(cfg, *, late):
    """Вариант, текст которого печатает посторонний. late: появляется сам, а не сразу."""
    voice = cfg["voice"]
    return Option(
        "bypass",
        "[ ? ]",
        voice["lines"],
        keys=("?", "/"),
        style="warning",
        late={"after_ms": voice["after_ms"], "typo": True, "settle_ms": 500} if late else None,
        rewrites={"after_ms": voice["again_after_ms"], "labels": voice["again_lines"]} if late else None,
    )


# ---------- сцены ----------

def intro_scene(cfg, hid):
    """Этапы 1-4: подключение и вход. Заканчивается выбором."""
    s = Scene()

    # 1. link
    _header(s, cfg, target=True)
    _stage(s, 1, "link")
    s.dots("resolving ", cfg["address"], "dim", ms=700)
    s.route(cfg["route"])
    s.dots("link      establishing ", "OK", ms=600)
    _next_screen(s)

    # 2. key exchange
    _header(s, cfg)
    _stage(s, 2, "key exchange")
    s.kv("cipher", cfg["key_exchange"]["cipher"], "dim")
    s.dots("client    generating key pair ", "OK", ms=700)
    s.dots("node      requesting public key ", "OK", ms=900)
    s.kv("key id", cfg["key_exchange"]["key_id"], "dim")
    s.progress("session   deriving key ", ms=1700)
    s.dots("session   key accepted ", "OK", ms=450)
    _next_screen(s)

    # 3. node
    _header(s, cfg)
    _stage(s, 3, "node")
    s.kv("chassis", hid, "dim")
    s.kv("system", cfg["system"])
    s.kv("owner", Scene.mask(cfg["owner_mask"]), note="[restricted]")
    s.newline()
    s.line("Node unrecognised. No prior contact on record.")
    s.pause(500)
    s.text("Trust node and continue? [y/n] ")
    s.pause(700, jitter=300)
    s.type("y", human=True)       # игрок «набрал» сам
    s.newline()
    s.line("Node added to contacts.", style="dim")
    _next_screen(s)

    # 4. access
    _header(s, cfg, chassis=hid)
    _stage(s, 4, "access")
    s.newline()
    s.line("-- node notice --", style="dim")
    for row in cfg["notice"]:
        s.line(row, style="dim")
    s.newline()
    s.kv("access", "external authority")
    s.newline()
    s.choice("entry", [_discord_option(cfg), _voice_option(cfg, late=True)])
    return s


def menu_scene(cfg):
    """Выбор снова, без сюжета (после неудачного обходного входа)."""
    return Scene().newline().choice("entry", [_discord_option(cfg), _voice_option(cfg, late=False)])


def discord_scene(cfg):
    return (
        Scene()
        .newline()
        .text("> requesting external authority: ")
        .text(cfg["external"], "dim")
        .newline()
        .pause(250)
        .line("Redirecting ...")
    )


def bypass_scene(cfg, hid):
    """Игрок пошёл за фразой. Имя узла в шапке портится прямо на месте, chassis остаётся.

    Сессию ещё не открыли: это делает established_scene после ответа сервера.
    """
    s = Scene()
    s.flash()
    s.pause(120)
    s.glitch("host", cfg["null_host"], frames=28)   # только main -> null: «aether-» остаётся
    s.pause(1100)                                    # дать увидеть, что стало
    _next_screen(s)

    _header(s, cfg, host=cfg["null_host"], chassis=hid)
    _stage(s, 5, "session")
    s.dots("access    ", "OPEN", "warning", ms=550)
    return s


def established_scene(clearance):
    """Сервер открыл гостевую сессию: заканчиваем подключение. Играется только после успеха."""
    s = Scene()
    s.dots("display   negotiating 1280x720 ", "OK", ms=600)
    s.dots("first frame ", "OK", ms=450)
    s.line("session established.", style="success")

    s.newline()
    s.kv("user", "guest", "dim")
    s.kv("clearance", f"{clearance['level']} ({clearance['label']})", "warning")
    s.line("WARNING: session is not registered on this node", style="warning")
    s.newline()
    s.line("Loading workspace")
    return s


def error_scene(cfg):
    """Обходной вход не удался: имя возвращается. {code} подставляет браузер."""
    return (
        Scene()
        .newline()
        .glitch("host", cfg["host"], frames=20)
        .line("ERROR: access refused ({code})", style="error")
    )


def restored_scene(cfg, hid, *, username, clearance, guest):
    """У игрока уже есть сессия: короткое подключение и идём дальше."""
    host = cfg["null_host"] if guest else cfg["host"]
    s = Scene()
    _header(s, cfg, host=host, chassis=hid)
    s.newline()
    s.dots("session   restoring ", "OK", ms=500)
    s.newline()
    s.kv("user", username, "dim" if guest else "success")
    s.kv("clearance", f"{clearance['level']} ({clearance['label']})", "warning" if guest else "success")
    if guest:
        s.line("Unregistered session: not on this node's account list.", style="warning")
    s.newline()
    s.line("Loading workspace")
    return s
