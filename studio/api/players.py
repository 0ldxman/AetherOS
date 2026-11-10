"""Игроки: список, карточка и действия автора с игроком. Логика в team.players, права в team.rights (раздел «Игроки»)."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from team import players as logic

router = Router(tags=["players"])


class PlRow(Schema):
    id: int
    username: str
    discord: str
    staff: bool
    banned: bool
    online: bool
    seen_at: dt.datetime | None
    accounts: int
    files: int


class PlAccount(Schema):
    id: int
    login: str
    hostname: str
    machine: int
    own: bool                    # рабочая учётка игрока (привязана к нему)
    online: bool
    seen_at: dt.datetime | None
    locked: int                  # секунд блокировки (0: нет)


class PlKey(Schema):
    account: int
    login: str
    hostname: str
    name: str
    slug: str


class PlMachineFiles(Schema):
    machine: int
    hostname: str
    count: int


class PlFile(Schema):
    hostname: str
    volume: str
    path: str
    kind: str
    at: dt.datetime


class PlEvent(Schema):
    at: dt.datetime
    label: str
    login: str
    hostname: str
    source: str
    detail: str


class PlCard(Schema):
    id: int
    username: str
    discord: str
    staff: bool
    banned: bool
    online: bool
    joined: dt.datetime
    last_login: dt.datetime | None
    accounts: list[PlAccount]
    keys: list[PlKey]
    machines: list[PlMachineFiles]
    files: list[PlFile]
    events: list[PlEvent]


class PlAccountIn(Schema):
    account: int


class PlKeyIn(Schema):
    account: int
    key: str = ""
    name: str = ""


class PlResetIn(Schema):
    machine: int | None = None


class PlBanIn(Schema):
    banned: bool


class PlDone(Schema):
    detail: str


def _player(player_id):
    return get_object_or_404(get_user_model().objects.prefetch_related("socialaccount_set"), pk=player_id, is_superuser=False)


def _call(fn):
    try:
        return fn()
    except logic.PlayerError as exc:
        raise HttpError(400, str(exc))


def _card(user):
    data = logic.card(user)
    return PlCard(
        id=user.pk, username=user.get_username(), discord=data["discord"], staff=user.is_staff, banned=not user.is_active,
        online=data["online"], joined=user.date_joined, last_login=user.last_login,
        accounts=[PlAccount(id=r["profile"].pk, login=r["profile"].login, hostname=r["profile"].machine.hostname,
                            machine=r["profile"].machine_id, own=r["own"], online=r["online"], seen_at=r["seen_at"], locked=r["locked"])
                  for r in data["accounts"]],
        keys=[PlKey(account=k["profile"].pk, login=k["profile"].login, hostname=k["profile"].machine.hostname, name=k["name"], slug=k["slug"])
              for k in data["keys"]],
        machines=[PlMachineFiles(**m) for m in data["machines"]],
        files=[PlFile(**f) for f in data["files"]],
        events=[PlEvent(at=e.at, label=e.get_kind_display(), login=e.profile.login, hostname=e.profile.machine.hostname,
                        source=e.source, detail=e.detail) for e in data["events"]],
    )


@router.get("", response=list[PlRow])
def player_list(request, q: str = "", online: bool = False):
    return [PlRow(id=u.pk, username=u.get_username(), discord=logic._discord(u), staff=u.is_staff, banned=not u.is_active,
                  online=u.online_now > 0, seen_at=u.seen, accounts=u.accounts, files=u.files)
            for u in logic.players(q.strip(), online)]


@router.get("/{int:player_id}", response=PlCard)
def player_card(request, player_id: int):
    return _card(_player(player_id))


@router.post("/{int:player_id}/kick", response=PlCard)
def kick(request, player_id: int, body: PlAccountIn):
    user = _player(player_id)
    _call(lambda: logic.kick(user, body.account))
    return _card(user)


@router.post("/{int:player_id}/unlock", response=PlCard)
def unlock(request, player_id: int, body: PlAccountIn):
    user = _player(player_id)
    _call(lambda: logic.unlock(user, body.account))
    return _card(user)


@router.post("/{int:player_id}/keys", response=PlCard)
def give_key(request, player_id: int, body: PlKeyIn):
    user = _player(player_id)
    _call(lambda: logic.give_key(user, body.account, body.key.strip()))
    return _card(user)


@router.post("/{int:player_id}/keys/take", response=PlCard)
def take_key(request, player_id: int, body: PlKeyIn):
    user = _player(player_id)
    _call(lambda: logic.take_key(user, body.account, body.name))
    return _card(user)


@router.post("/{int:player_id}/reset", response=PlCard)
def reset(request, player_id: int, body: PlResetIn):
    user = _player(player_id)
    logic.reset(user, body.machine)
    return _card(user)


@router.post("/{int:player_id}/ban", response=PlCard)
def ban(request, player_id: int, body: PlBanIn):
    user = _player(player_id)
    _call(lambda: logic.ban(request.user, user, body.banned))
    return _card(user)
