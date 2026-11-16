"""Словарь действий движка для Студии: какие действия есть, их поля и что можно выбрать в полях. Логика в engine/actions.py."""
from ninja import Router, Schema

router = Router(tags=["engine"])


class EnOption(Schema):
    value: str
    label: str


class EnField(Schema):
    name: str
    label: str
    kind: str
    placeholder: str
    required: bool
    options: list[EnOption]


class EnAction(Schema):
    name: str
    label: str
    needs: str
    group: str
    summary: str
    fields: list[EnField]


class EnCatalog(Schema):
    actions: list[EnAction]
    picks: dict[str, list[EnOption]]       # вид поля (key, letter, item, section, character, station, flag, world_flag, counter) → варианты


def _offer_picks(option):
    """Возможности всех сценариев: ноды-сущности «Возможность» — «слаг:нода» и подпись."""
    from graph import offers, runtime
    from graph.models import Graph

    found = []
    for graph in Graph.objects.filter(owner="").order_by("title"):
        doc = runtime.doc_of(graph)
        for node_id, node in doc.nodes.items():
            if node.get("type") == offers.ENTITY:
                data = doc.data(node_id)
                title = str(data.get("title") or data.get("command") or "").strip() or node_id
                found.append(option(offers.key(graph, node_id), f"{graph.title} · {title}"))
    return found


def _picks():
    from air.models import Station
    from characters.models import Character
    from filesystem.models import KEY_FORMAT, Item
    from forum.models import Section
    from graph.models import Graph
    from django.contrib.auth import get_user_model
    from zoneinfo import available_timezones

    from machines.models import Machine, NetResource, SystemType
    from machines.models.scenes import SceneScript
    from engine.models import Value
    from world import state
    from world.models import WorldMoment

    items = list(Item.objects.order_by("slug").values_list("slug", "format", "name"))
    sections = list(Section.objects.filter(archived=False).select_related("space"))
    by_id = {row.pk: row for row in sections}

    def path(row):
        parts = []
        while row is not None:
            parts.append(row.title)
            row = by_id.get(row.parent_id)
        return " / ".join(parts[::-1])

    option = lambda value, label=None: EnOption(value=str(value), label=label or str(value))      # noqa: E731
    return {
        "key": [option(slug, f"{slug} · {name}" if name and name != slug else slug) for slug, fmt, name in items if fmt == KEY_FORMAT],
        "letter": [option(slug, f"{slug} · {name}" if name and name != slug else slug) for slug, fmt, name in items if fmt == "msg"],
        "item": [option(slug, f"{slug} · {name}" if name and name != slug else slug) for slug, fmt, name in items if fmt != KEY_FORMAT],
        "section": sorted((option(row.pk, f"{row.space.title}: {path(row)}") for row in sections), key=lambda o: o.label),
        "character": [option(c.code, f"{c.code} · {c.signature}") for c in Character.objects.order_by("code")],
        "station": [option(name) for name in Station.objects.order_by("name").values_list("name", flat=True)],
        "flag": [option(name) for name in Value.objects.filter(kind="tag", owner="player").order_by("name").values_list("name", flat=True).distinct()],
        "world_flag": [option(name) for name in state.names("tag")],
        "offer": _offer_picks(option),
        "counter": [option(name) for name in state.names("count")],
        "object": [option(slug, f"{slug} · {name}" if name and name != slug else slug) for slug, fmt, name in items],
        "machine": [option(host, f"{host} · {name}" if name and name != host else host)
                    for host, name in Machine.objects.exclude(hostname="").order_by("hostname").values_list("hostname", "name")],
        "scene": [option(slug, f"{slug} · {title}" if title else slug) for slug, title in SceneScript.objects.order_by("slug").values_list("slug", "title")],
        "graph": [option(slug, f"{slug} · {title}") for slug, title in Graph.objects.order_by("slug").values_list("slug", "title")],
        "moment": [option(name, f"{name} · {title}" if title else name) for name, title in WorldMoment.objects.order_by("name").values_list("name", "title")],
        "server": [option(address, f"{address} · {title}" if title else address)
                   for address, title in NetResource.objects.order_by("address").values_list("address", "title")],
        "player": [option(name) for name in get_user_model().objects.filter(is_staff=False).order_by("username").values_list("username", flat=True)[:300]],
        "system": [option(code, f"{code} · {name}" if name and name != code else code) for code, name in SystemType.objects.order_by("code").values_list("code", "name")],
        "time_zone": [option(zone) for zone in sorted(available_timezones()) if "/" in zone or zone == "UTC"],
    }


@router.get("/catalog", response=EnCatalog)
def catalog(request):
    from engine import actions

    return EnCatalog(actions=actions.catalog(), picks=_picks())


class EnPlace(Schema):
    what: str
    label: str
    href: str


class EnLink(Schema):
    kind: str
    name: str
    level: str
    problem: str
    required: list[EnPlace]
    granted: list[EnPlace]
    manual: list[EnPlace]


@router.get("/links", response=list[EnLink])
def links(request):
    """Карта связей: что где требуется и что где выдаётся, с разрывами (engine/links.py)."""
    from engine import links as found

    convert = lambda places: [EnPlace(what=p.what, label=p.label, href=p.href) for p in places]      # noqa: E731
    return [EnLink(kind=row.kind, name=row.name, level=row.level, problem=row.problem, required=convert(row.required),
                   granted=convert(row.granted), manual=convert(row.manual)) for row in found.analyze()]
