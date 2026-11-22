"""Шина событий. Механика сообщает, что случилось: emit("key.got", user, machine=…, login=…, slug=…). Событие пишется в ленту
(engine.models.Event) — из неё журнал игрока; дальше на события встают сценарии. Отправка события никогда не ломает игру.

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
    "layer.added": "Файлу добавлен слой",
    "air.sent": "Передача в эфир",
    "mail.read": "Прочитал письмо",
    "forum.posted": "Написал на форуме",
    "machine.login": "Вошёл на машину",
    "machine.logout": "Вышел с машины",
    "world.flag": "Метка мира",
    "world.counter": "Счётчик мира",
    "moment.started": "Начался момент",
    "moment.ended": "Кончился момент",
    "flag.set": "Поставлена метка игрока",
    "flag.unset": "Снята метка игрока",
    "character.wrote": "Написал персонажу",
    "signal": "Сигнал сценария",
    "machine.stopped": "Машина остановлена",
    "machine.started": "Машина запущена",
    "machine.maintenance.started": "Машина ушла на обслуживание",
    "machine.maintenance.ended": "Обслуживание машины кончилось",
    "net.request": "Запросил страницу сервера",
    "net.download": "Скачал файл с сервера",
    "net.denied": "Сервер отказал",
    "command.run": "Выполнил команду",
    "player.counter": "Счётчик игрока",
    "object.got": "Объект попал к игроку",
    "machine.denied": "Отказ во входе",
    "graph.out": "Выход графа попытки",
    "file.changed": "Изменил файл",
    "file.moved": "Перенёс файл",
    "file.created": "Создал файл",
    "file.purged": "Стёр файл насовсем",
    "value.tag": "Тег изменился",
    "value.count": "Счётчик изменился",
    "offer.used": "Использовал возможность",
}


FIELDS = {                                  # какие подробности есть у события (для образца правила); у всех ещё host и login
    "key.got": ("slug", "path"),
    "key.joined": ("slug",),
    "file.read": ("path",),
    "file.deleted": ("path", "to"),
    "file.restored": ("path", "from"),
    "layer.removed": ("path", "layer", "id", "left"),
    "layer.attempt": ("path", "layer", "id", "left", "given"),
    "layer.failed": ("path", "layer", "id", "left"),
    "layer.added": ("path", "layer", "id", "left"),
    "air.sent": ("freq", "callsign", "text", "by", "character"),
    "mail.read": ("path", "subject", "sender", "item"),
    "forum.posted": ("section", "topic", "title"),
    "machine.login": (),
    "machine.logout": (),
    "world.flag": ("flag", "on"),
    "world.counter": ("counter", "value"),
    "moment.started": ("moment",),
    "moment.ended": ("moment",),
    "flag.set": ("flag",),
    "flag.unset": ("flag",),
    "character.wrote": ("character", "channel", "text", "subject", "sender", "message"),
    "signal": ("signal", "scope"),
    "machine.stopped": (),
    "machine.started": (),
    "machine.maintenance.started": (),
    "machine.maintenance.ended": (),
    "net.request": ("address", "path"),
    "net.download": ("address", "path"),
    "net.denied": ("address", "path", "reason"),
    "command.run": ("command", "args"),
    "player.counter": ("counter", "value"),
    "object.got": ("item", "path", "via"),
    "machine.denied": ("via", "reason"),
    "graph.out": ("owner", "socket"),
    "file.changed": ("item", "path"),
    "file.moved": ("item", "path", "from"),
    "file.created": ("item", "path", "via", "from"),
    "file.purged": ("item", "path"),
    "value.tag": ("owner", "thing", "key", "on", "per"),
    "value.count": ("owner", "thing", "key", "value", "delta", "per"),
    "offer.used": ("offer", "group", "result", "outs", "words", "forks", "text", "to", "placement", "attachment"),
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
    """Записать событие и разбудить сценарии. machine — объект машины или имя хоста. Возвращает событие или None, если записать не вышло."""
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
        from graph import runtime

        runtime.dispatch(event)
    except Exception:                                   # noqa: BLE001 — сломанный сценарий не роняет игру
        log.exception("graph on %s failed", name)
    return event


_heard = {"at": 0.0, "names": frozenset()}


def heard(name):
    """Слушает ли событие хоть один сценарий (для частых событий вроде command.run: не писать их зря)."""
    import time

    if time.monotonic() - _heard["at"] > 10:
        from graph.models import Start, Wait

        names = set(Start.objects.filter(graph__active=True).values_list("event", flat=True))
        names |= set(Wait.objects.filter(kind="event").values_list("event", flat=True))
        _heard.update(at=time.monotonic(), names=frozenset(names))
    return name in _heard["names"]


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
        "layer.added": lambda: f"{data.get('path', '')} · {data.get('layer', '')}",
        "offer.used": lambda: f"{data.get('offer', '')} → {data.get('result', '')}",
        "air.sent": lambda: f"{data.get('freq', '')} · {data.get('text', '')}",
        "mail.read": lambda: f"{data.get('sender', '')} · {data.get('subject', '')}",
        "forum.posted": lambda: data.get("title", ""),
        "machine.login": lambda: "",
        "machine.logout": lambda: "",
        "world.flag": lambda: f"world:{data.get('flag', '')} {'поставлена' if data.get('on') else 'снята'}",
        "world.counter": lambda: f"world:{data.get('counter', '')} → {data.get('value', '')}",
        "moment.started": lambda: data.get("moment", ""),
        "moment.ended": lambda: data.get("moment", ""),
        "flag.set": lambda: f"tag:{data.get('flag', '')}",
        "flag.unset": lambda: f"tag:{data.get('flag', '')}",
        "character.wrote": lambda: f"{data.get('character', '')} · {data.get('channel', '')} · {data.get('text', '')}",
        "signal": lambda: data.get("signal", ""),
        "machine.stopped": lambda: event.host,
        "machine.started": lambda: event.host,
        "machine.maintenance.started": lambda: event.host,
        "machine.maintenance.ended": lambda: event.host,
        "net.request": lambda: f"{data.get('address', '')}/{data.get('path', '')}",
        "net.download": lambda: f"{data.get('address', '')}/{data.get('path', '')}",
        "net.denied": lambda: f"{data.get('address', '')}/{data.get('path', '')} · {data.get('reason', '')}",
        "command.run": lambda: f"{data.get('command', '')} {data.get('args', '')}".strip(),
        "player.counter": lambda: f"count:{data.get('counter', '')} → {data.get('value', '')}",
        "object.got": lambda: f"{data.get('path', '')} · {data.get('via', '')}",
        "machine.denied": lambda: f"{event.login}@{event.host} · {data.get('reason', '')}",
        "graph.out": lambda: f"{data.get('owner', '')} · {data.get('socket', '')}",
        "file.changed": lambda: data.get("path", ""),
        "file.moved": lambda: f"{data.get('from', '')} → {data.get('path', '')}",
        "file.created": lambda: data.get("path", ""),
        "file.purged": lambda: data.get("path", ""),
        "value.tag": lambda: f"{data.get('owner', '')}{':' + str(data['thing']) if data.get('thing') else ''}:{data.get('key', '')} "
                             f"{'поставлен' if data.get('on') else 'снят'}",
        "value.count": lambda: f"{data.get('owner', '')}{':' + str(data['thing']) if data.get('thing') else ''}:{data.get('key', '')} → {data.get('value', '')}",
    }.get(event.name, lambda: "")()
    return f"{title}: {detail}" if detail else title
