"""Чёрный экран рабочего стола: подключение (arrive), закрытие подключения (leave), обрыв по сроку (kick).

Что показывать, решает ОС машины (SystemBlackout), пустые поля заполняет движок. Текст и заголовок с подстановками
{label} {host} {login} {os} {os_name}: цвет у окна один на всё окно (tone), поэтому цветовых тегов здесь нет."""
from scenes import markup

EVENTS = {"arrive": "Подключение", "leave": "Закрытие подключения", "kick": "Обрыв по сроку"}
TONES = ("success", "warning", "error", "dim")
PARAMS = {"label": "учётка@хост", "host": "хост", "login": "логин", "os": "код ОС", "os_name": "название ОС"}

RADIO = "AETHER"          # у Aether радио, у остальных ОС обычная сеть
_TONE = {"arrive": "success", "leave": "dim", "kick": "error"}
_TIMING = {"arrive": (500, 24, 900), "leave": (500, 24, 900), "kick": (1500, 32, 2600)}      # пауза до окна, мс на букву, пауза после
_TITLE = {"arrive": "{label} - connection established", "leave": "{label} - connection closed", "kick": "{label} - connection closed"}
_TEXT = {
    "arrive": ("carrier locked: {host}\nsession opened as {login}", "Connected to {host}.\nsession opened as {login}"),
    "leave": ("carrier released: {host}", "Connection to {host} closed."),
    "kick": ("carrier lost: {host}\nsession time limit exceeded", "Connection to {host} closed by remote host.\nsession time limit exceeded"),
}


def defaults(event, system):
    """Что показывается, если у ОС своего значения нет."""
    delay, speed, hold = _TIMING[event]
    return {
        "title": _TITLE[event], "text": _TEXT[event][0 if system == RADIO else 1], "tone": _TONE[event],
        "delay_ms": delay, "speed_ms": speed, "hold_ms": hold,
    }


def _plain(template, params):
    """Шаблон -> обычный текст (цвета не поддерживаются)."""
    return "\n".join("".join(text for text, _ in markup.parse_line(line, params)[0]) for line in template.splitlines())


def check(*templates):
    """Ошибки шаблонов: неизвестные подстановки и цветовые теги."""
    problems = []
    for template in templates:
        problems += [f"Строка {number}: {text}" for number, text in markup.check(template, PARAMS)]
        if any(style for line in template.splitlines() for _, style in markup.parse_line(line, dict.fromkeys(PARAMS))[0]):
            problems.append("Цвета здесь не поддерживаются: окно красится целиком (поле «Цвет»).")
    return problems


def values(event, system):
    """Значения события для ОС: свои поверх умолчаний движка."""
    from machines.models import SystemBlackout

    found = defaults(event, system)
    row = SystemBlackout.objects.filter(system_type__code=system, event=event).first()
    if row:
        for name in found:
            if getattr(row, name) not in ("", None):
                found[name] = getattr(row, name)
    return found


def resolve(event, profile, message=""):
    """Данные чёрного экрана для браузера. message: свой текст записи (важнее текста ОС)."""
    machine = profile.machine
    found = values(event, machine.system)
    system = machine.system_type
    params = {
        "label": f"{profile.login}@{machine.hostname}", "host": machine.hostname, "login": profile.login,
        "os": machine.system, "os_name": system.name if system else "",
    }
    return {
        "title": _plain(found["title"], params), "text": message or _plain(found["text"], params), "tone": found["tone"],
        "delay": found["delay_ms"], "speed": found["speed_ms"], "hold": found["hold_ms"],
    }


def effect(event, profile, message=""):
    """Эффект ответа терминала: показать чёрный экран и перезагрузить рабочий стол."""
    return {"op": "blackout", **resolve(event, profile, message)}
