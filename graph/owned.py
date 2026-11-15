"""Графы у вещей: как машина решает попытку входа, сервер — запрос.

Граф принадлежит вещи (Graph.owner = «вид:номер»), один на вещь и вид попытки. Его открывают из ноды попытки в сценарии
(«Машина: Попытка входа», Tab) или с экрана вещи. Внутри стартовая нода «Попытка» с подробностями, дальше всё, кроме ожиданий,
конец — «Ответить». Нет графа или ответа — решают поля вещи, как раньше.
"""
import logging

log = logging.getLogger("graph")

# вид попытки -> (владелец в engine.values, подпись графа, стартовая нода внутри)
KINDS = {
    "machine": ("machine", "Вход на машину", "attempt:machine"),
    "net.request": ("server", "Запрос к серверу", "attempt:server"),
    "net.download": ("server", "Скачивание с сервера", "attempt:server"),
}


def owner_of(kind, thing):
    """«machine:12» по вещи или её ключу (хост, адрес…). None — нет такой вещи."""
    from engine import values

    if kind not in KINDS:
        return None
    pk = values.owner_id(KINDS[kind][0], thing)
    return f"{kind}:{pk}" if pk is not None else None


def _label(kind, owner):
    from engine import values

    parts = owner.split(":")
    return values.owner_key(KINDS[kind][0], int(parts[1]))


def find(owner):
    from graph.models import Graph

    return Graph.objects.filter(owner=owner).first() if owner else None


def ensure(kind, thing):
    """Граф попытки вещи; нет — создаётся со стартовой нодой «Попытка». None — нет такой вещи."""
    from graph import runtime
    from graph.models import Graph

    owner = owner_of(kind, thing)
    if owner is None:
        return None
    found = find(owner)
    if found is not None:
        return found
    graph = Graph.objects.create(slug=owner.replace(":", "-").replace(".", "-").replace("*", "any")[:64], title=f"{KINDS[kind][1]}: {_label(kind, owner)}",
                                 active=True, owner=owner,
                                 doc={"nodes": [{"id": "start", "type": KINDS[kind][2], "x": 0, "y": 0, "data": {}}], "wires": []})
    runtime.rebuild_starts(graph)
    return graph


def decide(kind, thing, user, *, host="", login="", **data):
    """Спросить граф вещи о попытке: {"mode": allow|deny|block, "text", "minutes"} или None (решают поля вещи)."""
    graph = find(owner_of(kind, thing))
    if graph is None or not graph.active:
        return None
    from graph import runtime

    try:
        return runtime.decide(graph, user, host=host, login=login, **data)
    except Exception:                               # noqa: BLE001 — сломанный граф: дверь работает как обычно
        log.exception("graph %s decide failed", graph.owner)
        return None


def thing_of(doc, node_id):
    """Вещь ноды попытки: выбрана на ноде или пришла проводом с ноды сущности («Машина» с выбранной машиной). Иначе пусто."""
    from graph import nodes as N

    kind = doc.kind(node_id)
    if kind is None or not kind.owned:
        return ""
    field = kind.fields[0].name
    src = doc.refs.get((node_id, field))
    if src is None:
        return doc.data(node_id).get(field) or ""
    src_kind = doc.kind(src[0])
    if src_kind is None or src_kind.group != N.ENTITY or not src_kind.fields:
        return ""
    return doc.data(src[0]).get(src_kind.fields[0].name) or ""


def iface(owner):
    """Свои выходы графа попытки («Выход» внутри): сокеты ноды попытки снаружи."""
    from graph import runtime

    graph = find(owner)
    return runtime.iface(graph.doc) if graph is not None else {"inputs": [], "outputs": [], "in_types": {}, "out_types": {}}
