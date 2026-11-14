"""Шина событий. Механика сообщает, что случилось: emit("key.got", user, machine=…, login=…, slug=…). Событие пишется в ленту
(engine.models.Event) — из неё журнал игрока; дальше на события встанут правила. Отправка события никогда не ломает игру.

Имена событий (NAMES) — словарь для журнала и Студии; новое событие добавляется сюда же.
"""
import logging

log = logging.getLogger("engine")

NAMES = {
    "key.got": "Получил ключ",
    "key.joined": "Собрал ключ из частей",
    "file.read": "Открыл файл",
    "file.deleted": "Удалил файл",
    "file.restored": "Вернул файл из корзины",
    "layer.removed": "Снял слой с файла",
    "layer.attempt": "Неверная попытка снять слой",
    "layer.failed": "Попытки снять слой кончились",
    "mail.sent": "Написал персонажу",
    "air.sent": "Передал в эфир",
    "forum.posted": "Написал на форуме",
    "machine.login": "Вошёл на машину",
    "world.flag": "Метка мира",
    "world.counter": "Счётчик мира",
    "moment.started": "Начался момент",
    "moment.ended": "Кончился момент",
}


FIELDS = {                                  # какие подробности есть у события (для образца правила); у всех ещё host и login
    "key.got": ("slug", "path"),
    "key.joined": ("slug",),
    "file.read": ("path",),
    "file.deleted": ("path",),
    "file.restored": ("path",),
    "layer.removed": ("path", "layer"),
    "layer.attempt": ("path", "layer"),
    "layer.failed": ("path", "layer"),
    "mail.sent": ("to", "conversation", "step", "variant", "result"),
    "air.sent": ("freq", "callsign", "text"),
    "forum.posted": ("section", "topic", "title"),
    "machine.login": (),
    "world.flag": ("flag", "on"),
    "world.counter": ("counter", "value"),
    "moment.started": ("moment",),
    "moment.ended": ("moment",),
}


def _clean(value):
    """Подробности события только из простых значений: строки, числа, списки, словари."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value[:400] if isinstance(value, str) else value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_clean(item) for item in list(value)[:50]]
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    return str(value)[:400]


def emit(name, user=None, *, machine=None, login="", source="", **data):
    """Записать событие. machine — объект машины или имя хоста. Возвращает событие или None, если записать не вышло."""
    from engine.models import Event

    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    host = getattr(machine, "hostname", machine) or ""
    try:
        event = Event.objects.create(name=name[:40], user=user, host=str(host)[:64], login=str(login or "")[:64], source=str(source or "")[:200],
                                     data=_clean(data))
    except Exception:                                   # noqa: BLE001 — событие не должно ронять действие игрока
        log.exception("emit %s failed", name)
        return None
    try:
        from engine import rules

        rules.dispatch(event)
    except Exception:                                   # noqa: BLE001 — сломанное правило не роняет игру; причина в логе
        log.exception("rules on %s failed", name)
    if user is not None:
        try:
            from engine import chains

            chains.update(user)
        except Exception:                               # noqa: BLE001 — отметки цепочек не роняют игру
            log.exception("chains on %s failed", name)
    return event


def journal(user, limit=100):
    """Последние события игрока для карточки в Студии."""
    from engine.models import Event

    return list(Event.objects.filter(user=user)[:limit])


def describe(event):
    """Строка журнала: подпись события и главное из подробностей."""
    data = event.data or {}
    title = NAMES.get(event.name, event.name)
    detail = {
        "key.got": lambda: data.get("slug", ""),
        "key.joined": lambda: data.get("slug", ""),
        "file.read": lambda: data.get("path", ""),
        "file.deleted": lambda: data.get("path", ""),
        "file.restored": lambda: data.get("path", ""),
        "layer.removed": lambda: f"{data.get('path', '')} · {data.get('layer', '')}",
        "layer.attempt": lambda: f"{data.get('path', '')} · {data.get('layer', '')}",
        "layer.failed": lambda: f"{data.get('path', '')} · {data.get('layer', '')}",
        "mail.sent": lambda: f"{data.get('to', '')} · {data.get('variant', '')} → {data.get('result', '')}".strip(" ·→"),
        "air.sent": lambda: f"{data.get('freq', '')} · {data.get('text', '')}",
        "forum.posted": lambda: data.get("title", ""),
        "machine.login": lambda: "",
        "world.flag": lambda: f"world:{data.get('flag', '')} {'поставлена' if data.get('on') else 'снята'}",
        "world.counter": lambda: f"world:{data.get('counter', '')} → {data.get('value', '')}",
        "moment.started": lambda: data.get("moment", ""),
        "moment.ended": lambda: data.get("moment", ""),
    }.get(event.name, lambda: "")()
    return f"{title}: {detail}" if detail else title
