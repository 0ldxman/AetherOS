"""Цепочки загадок (engine/chains.py) для Студии: шаги-условия, воронка, кто где стоит, кто первым. Раздел прав «Мир»."""
import datetime as dt

from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from engine import chains as logic
from engine.models import Chain

router = Router(tags=["chains"])


class CnRow(Schema):
    id: int
    slug: str
    title: str
    steps: int
    active: bool


class CnStep(Schema):
    id: int | None = None
    title: str
    condition_text: str = ""
    hint: str = ""


class CnWaiting(Schema):
    player: str
    player_id: int
    since: dt.datetime
    days: float


class CnFunnel(Schema):
    reached: int
    first_player: str
    first_at: dt.datetime | None
    waiting: list[CnWaiting]
    breaks: list[str]


class CnDetail(Schema):
    id: int
    slug: str
    title: str
    note: str
    active: bool
    steps: list[CnStep]
    funnel: list[CnFunnel]
    players: int
    finished: list[str]


class CnIn(Schema):
    slug: str
    title: str
    note: str = ""
    active: bool = True
    steps: list[CnStep] = []


def _condition(text, number):
    from documents.markup.expr import SpoilerSyntaxError, parse_expr

    if not (text or "").strip():
        raise HttpError(400, f"Шаг {number}: нужно условие, когда он пройден.")
    try:
        return parse_expr(text)
    except SpoilerSyntaxError as error:
        raise HttpError(400, f"Шаг {number}: {error}") from None


def _apply(chain, body):
    from world import state

    try:
        chain.slug = state.check_name(body.slug)
    except state.WorldError as error:
        raise HttpError(400, str(error)) from None
    if Chain.objects.filter(slug=chain.slug).exclude(pk=chain.pk).exists():
        raise HttpError(400, "Цепочка с таким именем уже есть.")
    if not body.title.strip():
        raise HttpError(400, "Нужно название.")
    steps = []
    for number, step in enumerate(body.steps, 1):
        if not step.title.strip():
            raise HttpError(400, f"Шаг {number}: нужно название.")
        steps.append({"id": step.id, "title": step.title.strip()[:120], "condition": _condition(step.condition_text, number), "hint": step.hint.strip()[:300]})
    chain.title, chain.note, chain.active = body.title.strip()[:120], body.note, body.active
    chain.save()
    logic.save_steps(chain, steps)


def _detail(chain):
    from secure.access import format_condition

    logic.refresh(chain)
    report = logic.report(chain)
    return CnDetail(
        id=chain.pk, slug=chain.slug, title=chain.title, note=chain.note, active=chain.active, players=report["players"],
        steps=[CnStep(id=s.pk, title=s.title, condition_text=format_condition(s.condition) if s.condition else "", hint=s.hint) for s in chain.steps.all()],
        funnel=[CnFunnel(reached=row["reached"], first_player=row["first"][0].get_username() if row["first"] else "", first_at=row["first"][1] if row["first"] else None,
                         waiting=[CnWaiting(player=w["user"].get_username(), player_id=w["user"].pk, since=w["since"], days=round(w["days"], 1)) for w in row["waiting"]],
                         breaks=row["breaks"]) for row in report["steps"]],
        finished=[user.get_username() for user in report["finished"]],
    )


@router.get("", response=list[CnRow])
def chain_list(request):
    return [CnRow(id=c.pk, slug=c.slug, title=c.title, steps=c.steps.count(), active=c.active) for c in Chain.objects.all()]


@router.post("", response=CnDetail)
def create(request, body: CnIn):
    chain = Chain()
    _apply(chain, body)
    return _detail(chain)


@router.get("/{int:chain_id}", response=CnDetail)
def detail(request, chain_id: int):
    return _detail(get_object_or_404(Chain, pk=chain_id))


@router.put("/{int:chain_id}", response=CnDetail)
def update(request, chain_id: int, body: CnIn):
    chain = get_object_or_404(Chain, pk=chain_id)
    _apply(chain, body)
    return _detail(chain)


@router.delete("/{int:chain_id}", response={204: None})
def delete(request, chain_id: int):
    get_object_or_404(Chain, pk=chain_id).delete()
    return 204, None
