"""Пульт мира в Студии: мировые метки, счётчики с вкладами, триггеры, журнал; сборка ключей из частей. Логика в world/state.py и
secure/recipes.py, здесь обёртка."""
from datetime import datetime

from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from filesystem.models import KEY_FORMAT, Item
from secure import recipes
from secure.access import format_condition
from world import state
from world.models import WorldContribution, WorldCounter, WorldEvent, WorldFlag, WorldTrigger

router = Router(tags=["world-state"])


def _refuse(error):
    raise HttpError(400, str(error))


def _author(request):
    return f"автор {request.user.get_username()}"


class WsFlag(Schema):
    name: str
    label: str
    on: bool
    changed_at: datetime | None
    changed_by: str


class WsThreshold(Schema):
    value: int
    op: str
    trigger: str


class WsContribution(Schema):
    who: str
    delta: int
    source: str
    at: datetime


class WsCounter(Schema):
    name: str
    label: str
    mode: str
    value: int
    changed_at: datetime | None
    thresholds: list[WsThreshold]
    recent: list[WsContribution]
    players: int                 # сколько разных игроков вложилось


class WsTrigger(Schema):
    id: int
    name: str
    label: str
    condition: object
    condition_text: str
    actions: list[dict]
    repeat: bool
    active: bool
    was_true: bool
    fired_at: datetime | None
    fired_count: int


class WsEvent(Schema):
    at: datetime
    kind: str
    subject: str
    text: str
    source: str


class WsState(Schema):
    flags: list[WsFlag]
    counters: list[WsCounter]
    triggers: list[WsTrigger]
    events: list[WsEvent]


class WsFlagIn(Schema):
    name: str
    label: str = ""
    on: bool = False


class WsCounterIn(Schema):
    name: str
    label: str = ""
    mode: str = "sum"


class WsAmount(Schema):
    value: int


class WsTriggerIn(Schema):
    name: str
    label: str = ""
    condition_text: str
    actions: list[dict] = []
    repeat: bool = False
    active: bool = True


def _who(row):
    if row.user is None:
        return ""
    from air.radio import callsign_of

    return callsign_of(row.user).name


def _counter(row):
    recent = row.contributions.select_related("user")[:8]
    return WsCounter(name=row.name, label=row.label, mode=row.mode, value=row.value, changed_at=row.changed_at,
                     thresholds=[WsThreshold(value=v, op=op, trigger=t) for v, op, t in state.thresholds(row.name)],
                     recent=[WsContribution(who=_who(c), delta=c.delta, source=c.source, at=c.at) for c in recent],
                     players=row.contributions.exclude(user=None).values("user").distinct().count())


def _trigger(row):
    return WsTrigger(id=row.pk, name=row.name, label=row.label, condition=row.condition, condition_text=format_condition(row.condition),
                     actions=row.actions or [], repeat=row.repeat, active=row.active, was_true=row.was_true, fired_at=row.fired_at,
                     fired_count=row.fired_count)


@router.get("", response=WsState)
def read(request):
    return WsState(
        flags=[WsFlag(name=f.name, label=f.label, on=f.on, changed_at=f.changed_at, changed_by=f.changed_by) for f in WorldFlag.objects.all()],
        counters=[_counter(c) for c in WorldCounter.objects.all()],
        triggers=[_trigger(t) for t in WorldTrigger.objects.all()],
        events=[WsEvent(at=e.at, kind=e.kind, subject=e.subject, text=e.text, source=e.source) for e in WorldEvent.objects.all()[:60]],
    )


# ---------- метки ----------

@router.post("/flags", response=WsState)
def save_flag(request, body: WsFlagIn):
    try:
        name = state.check_name(body.name)
    except state.WorldError as error:
        _refuse(error)
    flag, _ = WorldFlag.objects.get_or_create(name=name)
    if flag.label != body.label.strip():
        flag.label = body.label.strip()[:200]
        flag.save(update_fields=["label"])
    state.set_flag(name, body.on, _author(request))
    return read(request)


@router.delete("/flags/{name}", response=WsState)
def delete_flag(request, name: str):
    flag = get_object_or_404(WorldFlag, name=name)
    if flag.on:
        state.set_flag(name, False, _author(request))
    flag.delete()
    return read(request)


# ---------- счётчики ----------

@router.post("/counters", response=WsState)
def save_counter(request, body: WsCounterIn):
    try:
        name = state.check_name(body.name)
    except state.WorldError as error:
        _refuse(error)
    if body.mode not in WorldCounter.Mode.values:
        _refuse("Режим: сумма вкладов или каждый игрок один раз.")
    counter, _ = WorldCounter.objects.get_or_create(name=name)
    counter.label, counter.mode = body.label.strip()[:200], body.mode
    counter.save(update_fields=["label", "mode"])
    return read(request)


@router.post("/counters/{name}/add", response=WsState)
def add_to_counter(request, name: str, body: WsAmount):
    get_object_or_404(WorldCounter, name=name)
    state.count(name, body.value, _author(request))
    return read(request)


@router.post("/counters/{name}/set", response=WsState)
def set_counter(request, name: str, body: WsAmount):
    get_object_or_404(WorldCounter, name=name)
    state.set_counter(name, body.value, _author(request))
    return read(request)


@router.delete("/counters/{name}", response=WsState)
def delete_counter(request, name: str):
    get_object_or_404(WorldCounter, name=name).delete()
    state.forget()
    return read(request)


# ---------- триггеры ----------

def _trigger_values(body):
    from documents.markup.expr import SpoilerSyntaxError, parse_expr

    try:
        name = state.check_name(body.name)
        condition = parse_expr(body.condition_text)
    except (state.WorldError, SpoilerSyntaxError) as error:
        _refuse(error)
    found = state.check_condition(condition) + state.check_actions(body.actions)
    if found:
        _refuse(found[0])
    if not body.actions:
        _refuse("Триггеру нужно хотя бы одно действие.")
    return {"name": name, "label": body.label.strip()[:200], "condition": condition, "actions": body.actions, "repeat": body.repeat, "active": body.active}


@router.post("/triggers", response=WsState)
def add_trigger(request, body: WsTriggerIn):
    values = _trigger_values(body)
    if WorldTrigger.objects.filter(name=values["name"]).exists():
        _refuse(f"Триггер {values['name']} уже есть.")
    trigger = WorldTrigger.objects.create(**values)
    WorldTrigger.objects.filter(pk=trigger.pk).update(was_true=state._truth(trigger.condition))   # уже верное условие не стреляет задним числом
    return read(request)


@router.put("/triggers/{int:trigger_id}", response=WsState)
def change_trigger(request, trigger_id: int, body: WsTriggerIn):
    trigger = get_object_or_404(WorldTrigger, pk=trigger_id)
    values = _trigger_values(body)
    if WorldTrigger.objects.filter(name=values["name"]).exclude(pk=trigger.pk).exists():
        _refuse(f"Триггер {values['name']} уже есть.")
    for name, value in values.items():
        setattr(trigger, name, value)
    trigger.was_true = state._truth(trigger.condition)
    trigger.save()
    return read(request)


@router.post("/triggers/{int:trigger_id}/fire", response=WsState)
def fire_trigger(request, trigger_id: int):
    state.fire(get_object_or_404(WorldTrigger, pk=trigger_id), by=_author(request))
    return read(request)


@router.post("/triggers/{int:trigger_id}/reset", response=WsState)
def reset_trigger(request, trigger_id: int):
    """Сбросить «уже срабатывал»: однократный снова сработает, когда условие станет верным."""
    WorldTrigger.objects.filter(pk=trigger_id).update(fired_count=0, fired_at=None, was_true=False)
    state.evaluate()
    return read(request)


@router.delete("/triggers/{int:trigger_id}", response=WsState)
def delete_trigger(request, trigger_id: int):
    get_object_or_404(WorldTrigger, pk=trigger_id).delete()
    return read(request)


# ---------- сборка ключа ----------

class WsPart(Schema):
    slug: str
    name: str
    sources: list[list[str]]       # [вид, где]


class WsRecipe(Schema):
    slug: str
    parts: list[WsPart]
    consume: bool
    part_of: list[list[str]]       # [итоговый ключ, «номер из всего»]


class WsRecipeIn(Schema):
    parts: list[str]
    consume: bool = False


class WsSplit(Schema):
    count: int
    consume: bool = False


def _key(slug):
    return get_object_or_404(Item, slug=slug, format=KEY_FORMAT)


def _recipe(item):
    recipe = recipes.recipe_of(item)
    parts = recipes.parts_of(recipe) if recipe else []
    return WsRecipe(slug=item.slug, consume=bool(recipe and recipe.consume),
                    parts=[WsPart(slug=p.slug, name=p.name, sources=[list(s) for s in recipes.sources(p)]) for p in parts],
                    part_of=[[r.slug, f"{n} из {t}"] for r, n, t in recipes.part_of(item)])


@router.get("/keys/{slug}/recipe", response=WsRecipe)
def recipe(request, slug: str):
    return _recipe(_key(slug))


@router.put("/keys/{slug}/recipe", response=WsRecipe)
def set_recipe(request, slug: str, body: WsRecipeIn):
    item = _key(slug)
    try:
        recipes.set_parts(item, body.parts, body.consume)
    except recipes.RecipeError as error:
        _refuse(error)
    return _recipe(item)


@router.post("/keys/{slug}/split", response=WsRecipe)
def split(request, slug: str, body: WsSplit):
    item = _key(slug)
    try:
        recipes.split(item, body.count, body.consume)
    except recipes.RecipeError as error:
        _refuse(error)
    return _recipe(item)
