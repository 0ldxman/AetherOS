"""Политики входа: список с тем, где каждая назначена, карточка с неделей окон и правка.

Окна проверяет тот же разбор, что у входа (machines/access/windows.py): ошибка в строке приходит с её номером, а неделю для
несохранённого текста можно посмотреть до сохранения.
"""
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from machines.access import windows
from machines.models import EntryPolicy

router = Router(tags=["policies"])

FIELDS = ("name", "description", "mode", "sources", "via", "max_attempts", "attempts_window", "lock_seconds", "ttl", "windows",
          "denied_text", "locked_text", "window_text", "kick_text")


class PolicyRow(Schema):
    id: int
    name: str
    description: str
    systems: int
    machines: int
    accounts: int


class PolicyUse(Schema):
    kind: str            # system | machine | account
    label: str
    machine: int | None


class PolicyOut(Schema):
    id: int
    name: str
    description: str
    mode: str
    sources: str
    via: str
    max_attempts: int | None
    attempts_window: int
    lock_seconds: int
    ttl: int | None
    windows: str
    denied_text: str
    locked_text: str
    window_text: str
    kick_text: str
    grid: list[list[bool]] | None
    used_by: list[PolicyUse]


class PolicyIn(Schema):
    name: str
    description: str = ""
    mode: str = "all"
    sources: str = ""
    via: str = ""
    max_attempts: int | None = None
    attempts_window: int = 600
    lock_seconds: int = 300
    ttl: int | None = None
    windows: str = ""
    denied_text: str = ""
    locked_text: str = ""
    window_text: str = ""
    kick_text: str = ""


class WindowsIn(Schema):
    windows: str


class Week(Schema):
    grid: list[list[bool]] | None
    error: str


def _grid(text):
    return windows.week(windows.parse(text)) if text.strip() else None


def _out(policy):
    used = [PolicyUse(kind="system", label=f"тип {code}", machine=None) for code in policy.system_types.values_list("code", flat=True)]
    used += [PolicyUse(kind="machine", label=machine.label, machine=machine.pk) for machine in policy.machines.all()]
    used += [PolicyUse(kind="account", label=f"{p.login}@{p.machine.label}", machine=p.machine_id) for p in policy.profiles.select_related("machine")]
    return PolicyOut(**{name: getattr(policy, name) for name in FIELDS}, id=policy.pk, grid=_grid(policy.windows), used_by=used)


@router.get("", response=list[PolicyRow])
def policies(request):
    rows = EntryPolicy.objects.order_by("name").annotate(
        system_count=Count("system_types", distinct=True), machine_count=Count("machines", distinct=True), account_count=Count("profiles", distinct=True),
    )
    return [PolicyRow(id=p.pk, name=p.name, description=p.description, systems=p.system_count, machines=p.machine_count, accounts=p.account_count)
            for p in rows]


@router.get("/{int:policy_id}", response=PolicyOut)
def read(request, policy_id: int):
    return _out(get_object_or_404(EntryPolicy, pk=policy_id))


def _save(policy, body):
    for name in FIELDS:
        setattr(policy, name, getattr(body, name))
    policy.full_clean()
    policy.save()
    return _out(policy)


@router.post("", response=PolicyOut)
def create(request, body: PolicyIn):
    return _save(EntryPolicy(), body)


@router.put("/{int:policy_id}", response=PolicyOut)
def save(request, policy_id: int, body: PolicyIn):
    return _save(get_object_or_404(EntryPolicy, pk=policy_id), body)


@router.delete("/{int:policy_id}")
def delete(request, policy_id: int):
    policy = get_object_or_404(EntryPolicy, pk=policy_id)
    if _out(policy).used_by:
        raise ValidationError("Политика назначена: сначала снимите её с типов, машин и учёток.")
    policy.delete()
    return {}


@router.post("/week", response=Week)
def week(request, body: WindowsIn):
    """Неделя окон для текста, который ещё не сохранён (редактор показывает её по мере набора)."""
    try:
        return Week(grid=_grid(body.windows), error="")
    except windows.WindowError as exc:
        return Week(grid=None, error=str(exc))
