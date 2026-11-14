"""Карта связей: что где требуется (условия во всех механиках) и что где выдаётся (действия, спрятанные ключи, сборки,
моменты). По ней видно разрывы загадок: ключ требуется, но его негде взять; метка ставится, но ни на что не влияет.

Факт — это (вид, имя): key — ключ, flag — метка игрока, world — метка мира, counter — счётчик мира.
Место — где он встречается: что это, подпись и адрес в Студии.
"""
import re
from dataclasses import dataclass, field

KINDS = ("key", "flag", "world", "counter")
SPOILER = re.compile(r"^::spoiler[ \t]+(.+?)[ \t]*$", re.M)


@dataclass(frozen=True)
class Place:
    what: str          # «вариант письма», «раздел форума», «правило»…
    label: str
    href: str = ""     # адрес в Студии (#/…)


@dataclass
class Fact:
    kind: str
    name: str
    required: list = field(default_factory=list)
    granted: list = field(default_factory=list)
    manual: list = field(default_factory=list)     # автор может поставить руками (пульт мира, выдача ключа в карточке)
    level: str = "ok"                              # ok, info, warning, error
    problem: str = ""


def atoms(condition):
    """(вид, имя) всех строк условия."""
    if not condition:
        return []
    if isinstance(condition, str):
        if condition.startswith("world:"):
            from world.state import WorldError, parse_atom

            try:
                name, op, _ = parse_atom(condition)
            except WorldError:
                return []
            return [("counter" if op else "world", name)]
        if condition.startswith("flag:"):
            return [("flag", condition[5:])]
        return [("key", condition)]
    if isinstance(condition, dict):
        found = []
        for value in condition.values():
            for part in value if isinstance(value, list) else [value]:
                found += atoms(part)
        return found
    return []


# ---------- что требуется ----------

def _requirements():
    """[(вид, имя, Place)] по всем местам с условиями."""
    from air.models import Band, Broadcast, Responder
    from engine.models import Rule
    from filesystem.models import Item, Placement, Volume
    from forum.models import Section, Space
    from machines.models import MachineProfile
    from machines.models.net import NetNode, NetResource
    from mail.models import Variant
    from map.models import MapScene
    from secure.models import KeyPart
    from world.models import WorldLetter, WorldMoment, WorldTrigger

    out = []

    def add(condition, place):
        out.extend((kind, name, place) for kind, name in atoms(condition))

    for item in Item.objects.exclude(access={}).only("pk", "name", "access"):
        add(item.access, Place("объект", item.name, f"#/items/{item.pk}"))
    for row in Placement.objects.exclude(access={}).select_related("item"):
        add(row.access, Place("размещение", str(row), f"#/items/{row.item_id}" if row.item_id else ""))
    for row in Volume.objects.exclude(access={}):
        add(row.access, Place("диск", str(row), f"#/volumes/{row.pk}"))
    for row in MachineProfile.objects.exclude(key_condition=None).select_related("machine"):
        add(row.key_condition, Place("учётка", f"{row.login}@{row.machine.hostname}", f"#/machines/{row.machine_id}/accounts"))
    for row in NetResource.objects.exclude(key_condition=None):
        add(row.key_condition, Place("адрес сети", row.address, ""))
    for row in NetNode.objects.exclude(key_condition=None):
        add(row.key_condition, Place("узел сети", str(row), ""))
    for row in MapScene.objects.exclude(key_condition=None):
        add(row.key_condition, Place("сцена карты", str(row), "#/map/scenes"))
    for row in Variant.objects.select_related("step__conversation"):
        place = Place("вариант письма", f"{row.step.conversation.slug} / {row.step.name}: {row.title}", f"#/mail/{row.step.conversation_id}")
        add(row.condition, place)
        out.extend(("flag", name, place) for name in row.need_flags or [])
        need = row.attachment or {}
        for slug in (need.get("key"), need.get("signed")):        # приложить ключ или файл, подписанный ключом: ключ нужен игроку
            if slug:
                out.append(("key", slug, place))
    for model, what in ((Band, "диапазон эфира"), (Broadcast, "передача по расписанию"), (Responder, "ответчик эфира")):
        for row in model.objects.exclude(condition=None):
            add(row.condition, Place(what, str(row), "#/air"))
    for space in Space.objects.all():
        for value in (space.read_if, space.write_if, space.create_if):
            add(value, Place("пространство форума", space.title, f"#/forum/{space.slug}"))
    for section in Section.objects.select_related("space"):
        for value in (section.read_if, section.write_if, section.create_if):
            add(value, Place("раздел форума", f"{section.space.title}: {section.title}", f"#/forum/{section.space.slug}/sections"))
    for row in WorldTrigger.objects.all():
        add(row.condition, Place("триггер", row.name, "#/world-state"))
    for row in WorldMoment.objects.exclude(condition=None):
        add(row.condition, Place("момент", row.name, "#/world-state"))
    for row in WorldLetter.objects.exclude(condition=None).select_related("item"):
        add(row.condition, Place("письмо всем", row.item.slug, ""))
    for row in Rule.objects.all():
        place = Place("правило", row.name, "#/rules")
        add(row.condition, place)
        watched = {"key.got": "key", "key.joined": "key", "world.flag": "world", "world.counter": "counter"}.get(row.on)
        name = (row.match or {}).get({"key": "slug", "world": "flag", "counter": "counter"}.get(watched, ""), "")
        if watched and name and not any(ch in str(name) for ch in "*?["):
            out.append((watched, str(name), Place("правило ждёт", row.name, "#/rules")))
    from engine.models import ChainStep

    for step in ChainStep.objects.select_related("chain"):
        add(step.condition, Place("шаг цепочки", f"{step.chain.title}: {step.title}", f"#/chains/{step.chain_id}"))
    for part in KeyPart.objects.select_related("recipe__result", "item"):
        out.append(("key", part.item.slug, Place("сборка ключа", f"часть {part.recipe.result.slug}", f"#/items/{part.recipe.result_id}")))
    out += _spoilers()
    return out


def _spoilers():
    from documents.markup.expr import SpoilerSyntaxError, parse_expr
    from filesystem.content.rawview import registry
    from filesystem.models import Item

    markup = {found.name for found in registry.all_formats() if found.markup}
    out = []
    for item in Item.objects.filter(format__in=markup, body__contains="::spoiler").only("pk", "name", "body"):
        for text in SPOILER.findall(item.body or ""):
            try:
                condition = parse_expr(text)
            except SpoilerSyntaxError:
                continue
            out.extend((kind, name, Place("спойлер в тексте", item.name, f"#/items/{item.pk}")) for kind, name in atoms(condition))
    return out


# ---------- что выдаётся ----------

def _action_lists():
    """[(действия, Place)] всех мест с действиями."""
    from air.models import Responder
    from engine.models import Rule
    from mail.models import Variant
    from world.models import WorldTrigger

    out = []
    for row in Variant.objects.select_related("step__conversation"):
        place = Place("исход письма", f"{row.step.conversation.slug} / {row.step.name}: {row.title}", f"#/mail/{row.step.conversation_id}")
        for actions in (row.outcomes or {}).values():
            out.append((actions, place))
    for row in Responder.objects.select_related("station"):
        out.append((row.actions, Place("ответчик эфира", str(row), "#/air")))
    for row in WorldTrigger.objects.all():
        out.append((row.actions, Place("триггер", row.name, "#/world-state")))
    for row in Rule.objects.all():
        out.append((row.actions, Place("правило", row.name, "#/rules")))
    return out


def _grants():
    """(выдачи [(вид, имя, Place)], ручные [(вид, имя, Place)])."""
    from engine.actions import refs
    from filesystem.models import KEY_FORMAT, ItemKey, Placement
    from secure.models import KeyRecipe
    from world.models import WorldCounter, WorldFlag, WorldMoment

    out = []
    for actions, place in _action_lists():
        for kind, name, role in refs(actions):
            if role == "grants" and kind in KINDS:
                out.append((kind, name, place))
    for link in ItemKey.objects.select_related("key", "item"):
        out.append(("key", link.key.slug, Place("спрятан в файле", link.item.name, f"#/items/{link.item_id}")))
    for row in Placement.objects.filter(item__format=KEY_FORMAT).select_related("item"):
        out.append(("key", row.item.slug, Place("лежит на диске", str(row), f"#/items/{row.item_id}")))
    for recipe in KeyRecipe.objects.select_related("result"):
        out.append(("key", recipe.result.slug, Place("сборка из частей", recipe.result.slug, f"#/items/{recipe.result_id}")))
    for moment in WorldMoment.objects.all():
        out.append(("world", moment.name, Place("момент", moment.title or moment.name, "#/world-state")))
    manual = [("world", name, Place("пульт мира", "вручную", "#/world-state")) for name in WorldFlag.objects.values_list("name", flat=True)]
    manual += [("counter", name, Place("пульт мира", "вручную", "#/world-state")) for name in WorldCounter.objects.values_list("name", flat=True)]
    return out, manual


# ---------- разбор ----------

def analyze():
    """Все факты с местами и проблемами, сначала проблемные."""
    from filesystem.models import KEY_FORMAT, Item

    facts = {}

    def fact(kind, name):
        return facts.setdefault((kind, name), Fact(kind, name))

    for kind, name, place in _requirements():
        if place not in fact(kind, name).required:
            fact(kind, name).required.append(place)
    granted, manual = _grants()
    for kind, name, place in granted:
        if place not in fact(kind, name).granted:
            fact(kind, name).granted.append(place)
    for kind, name, place in manual:
        if (kind, name) in facts:
            facts[(kind, name)].manual.append(place)

    keys = set(Item.objects.filter(format=KEY_FORMAT).values_list("slug", flat=True))
    for row in facts.values():
        if row.kind == "key" and row.name not in keys:
            row.level, row.problem = "error", "такого ключа нет в реестре"
        elif row.required and not row.granted and row.kind in ("key", "flag"):
            row.level, row.problem = "error", "требуется, но игроку его негде взять"
        elif row.required and not row.granted:
            row.level, row.problem = "warning", "ставится только вручную на пульте" if row.manual else "требуется, но ничто его не ставит"
        elif row.granted and not row.required:
            row.level, row.problem = "info", "выдаётся, но ни на что не влияет"
    order = {"error": 0, "warning": 1, "info": 2, "ok": 3}
    return sorted(facts.values(), key=lambda row: (order[row.level], KINDS.index(row.kind), row.name))
