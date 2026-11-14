"""Правила на события (engine/rules.py) для Студии: список, правка, кто сработал. Раздел прав «Мир»."""
import datetime as dt

from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from engine import events
from engine.models import Rule

router = Router(tags=["rules"])


class RuEventKind(Schema):
    name: str
    label: str
    fields: list[str]


class RuRule(Schema):
    id: int
    name: str
    label: str
    on: str
    match: dict[str, str]
    condition_text: str
    actions: list[dict]
    once: str
    active: bool
    fires: int
    first_player: str            # кто сработал первым («first decoded by»)
    first_at: dt.datetime | None
    last_at: dt.datetime | None


class RuList(Schema):
    rules: list[RuRule]
    events: list[RuEventKind]


class RuIn(Schema):
    name: str
    label: str = ""
    on: str
    match: dict[str, str] = {}
    condition_text: str = ""
    actions: list[dict] = []
    once: str = "player"
    active: bool = True


class RuFire(Schema):
    at: dt.datetime
    player: str


def _row(rule):
    from secure.access import format_condition

    fires = list(rule.fires.select_related("user").order_by("at", "id"))
    first = fires[0] if fires else None
    return RuRule(id=rule.pk, name=rule.name, label=rule.label, on=rule.on, match={k: str(v) for k, v in (rule.match or {}).items()},
                  condition_text=format_condition(rule.condition) if rule.condition else "", actions=rule.actions or [], once=rule.once,
                  active=rule.active, fires=len(fires), first_player=first.user.get_username() if first and first.user else "",
                  first_at=first.at if first else None, last_at=fires[-1].at if fires else None)


def _list():
    return RuList(rules=[_row(rule) for rule in Rule.objects.prefetch_related("fires")],
                  events=[RuEventKind(name=name, label=label, fields=[*events.FIELDS.get(name, ()), "host", "login"]) for name, label in events.NAMES.items()])


def _apply(rule, body):
    from documents.markup.expr import SpoilerSyntaxError, parse_expr
    from engine import actions as engine
    from engine.context import ACCOUNT, USER, WORLD
    from world import state

    try:
        rule.name = state.check_name(body.name)
    except state.WorldError as error:
        raise HttpError(400, str(error)) from None
    if Rule.objects.filter(name=rule.name).exclude(pk=rule.pk).exists():
        raise HttpError(400, "Правило с таким именем уже есть.")
    if body.on not in events.NAMES:
        raise HttpError(400, f"Нет такого события «{body.on}».")
    allowed = {*events.FIELDS.get(body.on, ()), "host", "login"}
    match = {key.strip(): value.strip() for key, value in body.match.items() if key.strip() and value.strip()}
    unknown = [key for key in match if key not in allowed]
    if unknown:
        raise HttpError(400, f"У события {body.on} нет поля «{unknown[0]}».")
    condition = None
    if body.condition_text.strip():
        try:
            condition = parse_expr(body.condition_text)
        except SpoilerSyntaxError as error:
            raise HttpError(400, f"Условие: {error}") from None
    problems = engine.check(body.actions, provides=(WORLD, USER, ACCOUNT))
    if problems:
        raise HttpError(400, problems[0])
    if body.once not in Rule.Once.values:
        raise HttpError(400, "Сколько раз: world, player или always.")
    rule.label, rule.on, rule.match, rule.condition = body.label.strip()[:200], body.on, match, condition
    rule.actions, rule.once, rule.active = body.actions, body.once, body.active
    rule.save()


@router.get("", response=RuList)
def rule_list(request):
    return _list()


@router.post("", response=RuList)
def create(request, body: RuIn):
    _apply(Rule(), body)
    return _list()


@router.put("/{int:rule_id}", response=RuList)
def update(request, rule_id: int, body: RuIn):
    _apply(get_object_or_404(Rule, pk=rule_id), body)
    return _list()


@router.delete("/{int:rule_id}", response=RuList)
def delete(request, rule_id: int):
    get_object_or_404(Rule, pk=rule_id).delete()
    return _list()


@router.post("/{int:rule_id}/reset", response=RuList)
def reset(request, rule_id: int):
    """Забыть срабатывания: правило снова «ничьё» (для проверки загадки)."""
    get_object_or_404(Rule, pk=rule_id).fires.all().delete()
    return _list()


@router.get("/{int:rule_id}/fires", response=list[RuFire])
def fires(request, rule_id: int):
    rule = get_object_or_404(Rule, pk=rule_id)
    return [RuFire(at=row.at, player=row.user.get_username() if row.user else "") for row in rule.fires.select_related("user").order_by("-at")[:100]]
