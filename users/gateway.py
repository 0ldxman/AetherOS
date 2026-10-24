"""Сцены экрана входа: игрок подключается к удалённой машине.

Это сцены консоли (console/scene.py), а не страница: Python собирает их, браузер
проигрывает (static/ui/console.js, desktop/static/boot/lock.js).

Сюжет. Игрок пробует зайти на aether-main. Вход там только через внешнюю
систему (Discord). Пока он смотрит, на машине кто-то другой, не игрок, пишет ему
сообщение и открывает обходной канал. Выбрав его, игрок видит, что имя узла
меняется на aether-null: для системы это две личности на одном корпусе, hid у
них общий.

ПРОТОТИП: данные в GATEWAY потом должны задаваться из админки (у каждой машины
свои). Организацию-владельца здесь НЕ указываем, а поле owner замазано: игрок
должен сам догадаться, чья это машина. Сцена целиком видна в исходнике страницы.
"""
from console.scene import Event, Option, Scene

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
    "notice": [
        "Authorized personnel only.",
        "All access is monitored and logged.",
    ],
    "owner_mask": 14,
    "external": "DISCORD",
    "channel": {"name": "maintenance", "port": 4721},
    "sender": "unregistered operator · tty3 · 03:12",
    # Первое лицо, случайная строка при каждом заходе
    "messages": [
        "i left it open for you",
        "come in. i'll keep it open",
        "i can let you in. quietly.",
        "you don't have to ask them",
        "this way. they aren't looking at this door",
        "i opened this for you. hurry",
    ],
    # Если игрок ничего не делает, спустя это время приходит ещё одно сообщение
    "nudge_after_ms": [20000, 30000],
    "nudges": [
        "...still here",
        "i can't hold this open for long",
        "are you there?",
    ],
    # Сообщение появляется через столько мс после того, как показаны варианты входа
    "event_after_ms": 2200,
}


def _discord_option(cfg):
    return Option("discord", "[ D ]", "external authority", tag=cfg["external"], keys=("d",))


def _bypass_option(cfg):
    return Option(
        "bypass",
        "[ ? ]",
        f"{cfg['channel']['name']} channel",
        tag="OPEN",
        keys=("?", "/"),
        style="warning",
    )


def _inbound(cfg, scene):
    """Входящее сообщение от постороннего оператора: типизируется «живым человеком»."""
    return (
        Scene()
        .newline()
        .line(f"-- inbound text · {cfg['sender']} --", style="warning")
        .extend(scene)
        .line("-- end --", style="dim")
    )


def intro_scene(cfg, hid):
    """Подключение к aether-main и вход; затем событие с обходным каналом."""
    s = Scene()
    s.line((cfg["client"], None), ("  ·  remote session client", "dim"))
    s.newline()
    s.kv("target", cfg["host"], note="(saved)")
    s.dots("resolving ", cfg["address"], "dim", ms=700)
    s.route(cfg["route"])
    s.pause(300)
    s.dots("session   negotiating ", "OK", ms=650)

    s.newline()
    s.kv("node", cfg["host"], id="host")
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

    s.newline()
    s.line("-- node notice --", style="dim")
    for row in cfg["notice"]:
        s.line(row, style="dim")
    s.pause(300)
    s.newline()
    s.kv("access", "external authority")
    s.newline()

    message = Scene().one_of(*[Scene().type(m, human=True, typo=True).newline() for m in cfg["messages"]])
    opened = (
        _inbound(cfg, message)
        .pause(500)
        .line(f"channel opened: {cfg['channel']['name']} · {cfg['channel']['port']}", style="warning")
        .kv("access", "external authority · open", style="warning")
        .newline()
    )
    nudge = Scene().one_of(*[Scene().type(n, human=True).newline() for n in cfg["nudges"]])

    s.choice(
        "entry",
        [_discord_option(cfg)],
        events=[
            Event(cfg["event_after_ms"], opened, (_bypass_option(cfg),)),
            Event(cfg["nudge_after_ms"], _inbound(cfg, nudge)),
        ],
    )
    return s


def menu_scene(cfg):
    """Выбор снова, без сюжета (после неудачного обходного входа)."""
    return Scene().newline().choice("entry", [_discord_option(cfg), _bypass_option(cfg)])


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
    """Нажат обходной канал: то же железо, другое имя. Сессию ещё не открыли (established_scene)."""
    port = cfg["channel"]["port"]
    s = Scene()
    s.newline()
    s.dots(f"connecting channel {port} ", "OK", "warning", ms=700)
    s.flash()
    s.pause(150)
    s.glitch("host", cfg["null_host"])

    s.newline()
    s.line("!! NODE IDENTITY MISMATCH !!", style="warning")
    s.kv("node", f"{cfg['host']}  ->  {cfg['null_host']}", "warning")
    s.kv("chassis", hid, note="(unchanged)")
    s.line("Two identities answer on one chassis.", style="dim")
    s.newline()
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
    port = cfg["channel"]["port"]
    return (
        Scene()
        .newline()
        .glitch("host", cfg["host"])
        .line(f"ERROR: channel {port} refused ({{code}})", style="error")
    )


def restored_scene(cfg, hid, *, username, clearance, guest):
    """У игрока уже есть сессия: короткое подключение и идём дальше."""
    host = cfg["null_host"] if guest else cfg["host"]
    s = Scene()
    s.line((cfg["client"], None), ("  ·  remote session client", "dim"))
    s.newline()
    s.kv("target", host, note="(saved)")
    s.kv("chassis", hid, "dim")
    s.dots("session   restoring ", "OK", ms=500)
    s.newline()
    s.kv("user", username, "dim" if guest else "success")
    s.kv("clearance", f"{clearance['level']} ({clearance['label']})", "warning" if guest else "success")
    if guest:
        s.line("Unregistered session: not on this node's account list.", style="warning")
    s.newline()
    s.line("Loading workspace")
    return s
