"""Машины: список, обзор (кто на машине, предупреждения, последние события), проверка входа, журнал и действия с игроками.

Решения принимает machines (machines.access.check, machines.access.entry, machines.network.bridge): здесь только схемы.
"""
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

from machines.access import check as checking
from machines.access import entry, groups
from machines.models import EntryPolicy, LoginEvent, Machine, MachineProfile, Session, SystemType
from machines.network import bridge
from machines.models.machine import generate_hid
from machines.world import identity
from machines.world.facts import ONLINE

router = Router(tags=["machines"])

REFUSALS = ("bad_password", "bad_key", "bad_token", "source", "route", "window", "locked")


class MachineRow(Schema):
    id: int
    hostname: str
    name: str
    system: str
    status: str
    is_system: bool
    accounts: int
    online: int
    refusals: int


class Policy(Schema):
    id: int
    name: str
    origin: str | None = None          # profile | machine | system (для действующей)


class AccountRow(Schema):
    id: int
    login: str
    name: str
    freq: str
    groups: list[str]
    root: bool
    has_password: bool
    has_key: bool
    tokens: int
    policy: Policy | None
    owner: str | None                   # игрок, чья это учётка (его рабочая машина)


class Online(Schema):
    session: int
    player: str
    account: int
    login: str
    seen_at: datetime
    locked: int                         # секунд блокировки (0: нет)


class Event(Schema):
    id: int
    at: datetime
    shown_at: datetime
    kind: str
    label: str
    login: str
    account: int
    player: str | None
    source: str
    detail: str


class Warning_(Schema):
    level: str                          # warning | info
    text: str
    account: int | None = None


class Overview(Schema):
    id: int
    hostname: str
    name: str
    system: str
    status: str
    hid: str
    address: str
    serial: str
    host_key: str
    auto_address: str           # что подставится, если поле пусто
    auto_serial: str
    auto_host_key: str
    randomart: list[str]        # картинка того ключа, который действует сейчас
    note: str
    booted_at: datetime | None
    is_system: bool
    policy: Policy | None
    accounts: list[AccountRow]
    online: list[Online]
    events: list[Event]
    warnings: list[Warning_]
    groups: list[str]
    policies: list[Policy]
    systems: list[str]
    statuses: list[str]


class MachineIn(Schema):
    hostname: str
    name: str
    system: str
    status: str
    hid: str | None = None      # None: не менять
    address: str = ""
    serial: str = ""
    host_key: str = ""
    note: str = ""
    booted_at: datetime | None = None
    entry_policy: int | None = None


class CheckIn(Schema):
    account: int
    source: str = ""
    chain: list[str] = []
    at: datetime | None = None
    player: str = ""
    password: str | None = None
    keys: list[str] = []
    token: str = ""


class Step(Schema):
    name: str
    ok: bool | None
    text: str


class Verdict(Schema):
    admitted: bool | None
    kind: str
    steps: list[Step]


class NewMachine(Schema):
    hostname: str
    name: str = ""
    system: str = "AETHER"
    status: str = "OFFLINE"
    root: str = "empty"                 # empty | template | volume | like
    template: int | None = None
    volume: int | None = None
    like: int | None = None             # машина-образец (root=like)


class MachineCreated(Schema):
    id: int


class PlayerAction(Schema):
    account: int
    player: str


def _machine(machine_id):
    return get_object_or_404(Machine, pk=machine_id)


def _policy(profile):
    origin, policy = checking.origin_of(profile)
    return Policy(id=policy.pk, name=policy.name, origin=origin) if policy else None


def _event(event):
    return Event(
        id=event.pk, at=event.at, shown_at=event.shown_at, kind=event.kind, label=event.get_kind_display(), login=event.profile.login,
        account=event.profile_id, player=event.user.get_username() if event.user_id else None, source=event.source, detail=event.detail,
    )


def _account_row(profile):
    return AccountRow(
        id=profile.pk, login=profile.login, name=profile.name, freq=f"{profile.freq:.3f}", groups=list(profile.groups or []),
        root=profile.root, has_password=bool(profile.password_hash), has_key=bool(profile.key_condition), tokens=profile.token_count,
        policy=_policy(profile), owner=profile.user.get_username() if profile.user_id else None,
    )


def _warnings(machine, accounts):
    found = []
    known = set(groups.effective(machine))
    for profile in accounts:
        if not profile.password_hash and not profile.key_condition and profile.user_id is None:
            found.append(Warning_(level="warning", account=profile.pk,
                                  text=f"У учётки {profile.login} нет ни пароля, ни ключа: войти может любой."))
        unknown = [name for name in profile.groups or [] if name not in known]
        if unknown:
            found.append(Warning_(level="warning", account=profile.pk,
                                  text=f"У учётки {profile.login} группы, которых нет на машине: {', '.join(unknown)}."))
    if not machine.hostname:
        found.append(Warning_(level="info", text="У машины нет имени хоста: к ней нельзя подключиться по имени."))
    if machine.status != Machine.Status.ONLINE:
        found.append(Warning_(level="info", text=f"Машина в статусе {machine.get_status_display()}."))
    return found


@router.get("", response=list[MachineRow])
def machines(request):
    since = timezone.now() - timedelta(hours=24)
    alive = timezone.now() - ONLINE
    rows = Machine.objects.order_by("hostname", "name").annotate(
        account_count=Count("profiles", distinct=True),
        online_count=Count("profiles__sessions", filter=Q(profiles__sessions__seen_at__gte=alive), distinct=True),
        refusal_count=Count("profiles__events", filter=Q(profiles__events__at__gte=since, profiles__events__kind__in=REFUSALS), distinct=True),
    )
    return [
        MachineRow(id=m.pk, hostname=m.hostname or "", name=m.name, system=m.system, status=m.status, is_system=m.is_system,
                   accounts=m.account_count, online=m.online_count, refusals=m.refusal_count)
        for m in rows
    ]


@router.post("", response=MachineCreated)
def create(request, body: NewMachine):
    """Новая машина: с нуля (корень пустой, по шаблону или готовый том) или по образцу другой машины (machines.world.create)."""
    from machines.world.create import clone_machine, create_machine

    if body.root == "like":
        machine = clone_machine(get_object_or_404(Machine, pk=body.like), body.hostname.strip(), body.name.strip(), body.status)
    else:
        machine = create_machine(body.hostname.strip(), body.name.strip(), body.system, body.status, body.root, body.template, body.volume)
    return MachineCreated(id=machine.pk)


@router.delete("/{int:machine_id}")
def delete(request, machine_id: int):
    machine = _machine(machine_id)
    if machine.is_system:
        raise ValidationError("Это системная машина: её нельзя удалить.")
    machine.delete()
    return {}


def _auto(machine):
    """Значения, которые действуют, пока поле пусто, и картинка действующего ключа."""
    hid = machine.hid
    return {
        "auto_address": identity.address_of(hid, machine.system), "auto_serial": identity.serial_for(hid),
        "auto_host_key": identity.fingerprint_for(hid), "randomart": list(identity.of_machine(machine).randomart),
    }


class GenerateIn(Schema):
    field: str          # hid | address | serial | host_key
    system: str = ""    # у радио-ОС адрес это частота


class Generated(Schema):
    value: str


class ArtIn(Schema):
    host_key: str


class Art(Schema):
    valid: bool
    lines: list[str]


@router.post("/generate", response=Generated)
def generate(request, body: GenerateIn):
    """Случайное значение для поля идентичности: подставляется в форму, сохраняется кнопкой «Сохранить»."""
    makers = {
        "hid": generate_hid, "serial": identity.generate_serial, "host_key": identity.generate_host_key,
        "address": lambda: identity.generate_address(body.system),
    }
    if body.field not in makers:
        raise ValidationError({"field": ["Нет такого поля."]})
    return Generated(value=makers[body.field]())


@router.post("/randomart", response=Art)
def randomart(request, body: ArtIn):
    """Картинка отпечатка для показа, пока ключ правят в форме."""
    key = body.host_key.strip()
    return Art(valid=bool(identity.FINGERPRINT.match(key)), lines=list(identity.randomart_of(key)))


@router.get("/{int:machine_id}", response=Overview)
def overview(request, machine_id: int):
    machine = _machine(machine_id)
    accounts = list(
        machine.profiles.select_related("user", "entry_policy", "machine__entry_policy").annotate(token_count=Count("tokens")).order_by("login", "freq")
    )
    sessions = Session.objects.filter(profile__machine=machine, seen_at__gte=timezone.now() - ONLINE).select_related("user", "profile")
    events = LoginEvent.objects.filter(profile__machine=machine).select_related("profile", "user").order_by("-at", "-id")[:15]
    machine_policy = machine.entry_policy if machine.entry_policy_id else None
    return Overview(
        id=machine.pk, hostname=machine.hostname or "", name=machine.name, system=machine.system, status=machine.status, hid=machine.hid,
        address=machine.address, serial=machine.serial, host_key=machine.host_key, **_auto(machine),
        note=machine.note, booted_at=machine.booted_at,
        is_system=machine.is_system,
        policy=Policy(id=machine_policy.pk, name=machine_policy.name, origin="machine") if machine_policy else None,
        accounts=[_account_row(profile) for profile in accounts],
        online=[
            Online(session=s.pk, player=s.user.get_username(), account=s.profile_id, login=s.profile.login, seen_at=s.seen_at,
                   locked=max(bridge.locked_for(s.user, s.profile), entry.locked_seconds(s.user, s.profile)))
            for s in sessions
        ],
        events=[_event(event) for event in events],
        warnings=_warnings(machine, accounts),
        groups=groups.choices(machine),
        policies=[Policy(id=p.pk, name=p.name) for p in EntryPolicy.objects.order_by("name")],
        systems=list(SystemType.objects.order_by("code").values_list("code", flat=True)) or [machine.system],
        statuses=[value for value, _ in Machine.Status.choices],
    )


@router.put("/{int:machine_id}", response=Overview)
def save(request, machine_id: int, body: MachineIn):
    machine = _machine(machine_id)
    machine.hostname = body.hostname.strip() or None
    machine.name = body.name
    machine.system = body.system
    machine.status = body.status
    machine.address, machine.serial, machine.host_key = body.address.strip(), body.serial.strip(), body.host_key.strip()
    machine.note, machine.booted_at = body.note, body.booted_at
    if body.hid is not None:
        machine.hid = body.hid.strip().lower()
    machine.entry_policy_id = body.entry_policy
    machine.full_clean()
    machine.save()
    return overview(request, machine_id)


@router.post("/{int:machine_id}/check", response=Verdict)
def check(request, machine_id: int, body: CheckIn):
    """Пустит ли учётка: те же правила, что у входа игрока, ничего не записывается."""
    profile = get_object_or_404(MachineProfile.objects.select_related("machine", "entry_policy"), pk=body.account, machine_id=machine_id)
    player = get_user_model().objects.filter(username=body.player).first() if body.player else None
    verdict = checking.check(
        profile, source=body.source.strip(), chain=[host.strip() for host in body.chain if host.strip()], at=body.at, player=player,
        password=body.password, keys={slug.strip() for slug in body.keys if slug.strip()}, token=body.token.strip() or None,
    )
    return Verdict(admitted=verdict.admitted, kind=verdict.kind, steps=[Step(**vars(step)) for step in verdict.steps])


@router.get("/{int:machine_id}/events", response=list[Event])
def events(request, machine_id: int, account: int | None = None, kind: str = "", player: str = "", days: int = 7):
    found = LoginEvent.objects.filter(profile__machine_id=machine_id, at__gte=timezone.now() - timedelta(days=max(1, min(days, 30))))
    if account:
        found = found.filter(profile_id=account)
    if kind:
        found = found.filter(kind__in=kind.split(","))
    if player:
        found = found.filter(user__username=player)
    return [_event(event) for event in found.select_related("profile", "user").order_by("-at", "-id")[:500]]


def _pair(machine_id, body):
    profile = get_object_or_404(MachineProfile, pk=body.account, machine_id=machine_id)
    return profile, get_object_or_404(get_user_model(), username=body.player)


@router.post("/{int:machine_id}/unlock")
def unlock(request, machine_id: int, body: PlayerAction):
    profile, player = _pair(machine_id, body)
    entry.unlock(profile, player)
    return {}


@router.post("/{int:machine_id}/kick")
def kick(request, machine_id: int, body: PlayerAction):
    profile, player = _pair(machine_id, body)
    return {"sessions": bridge.request_kick(player, profile)}
