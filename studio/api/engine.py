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


def _picks():
    from air.models import Station
    from characters.models import Character
    from filesystem.models import KEY_FORMAT, Item
    from forum.models import Section
    from mail.models import Flag
    from world.models import WorldCounter, WorldFlag

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
        "flag": [option(name) for name in Flag.objects.order_by("name").values_list("name", flat=True).distinct()],
        "world_flag": [option(name) for name in WorldFlag.objects.order_by("name").values_list("name", flat=True)],
        "counter": [option(name) for name in WorldCounter.objects.order_by("name").values_list("name", flat=True)],
    }


@router.get("/catalog", response=EnCatalog)
def catalog(request):
    from engine import actions

    return EnCatalog(actions=actions.catalog(), picks=_picks())
