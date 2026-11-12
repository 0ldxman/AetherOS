"""Настройки мира: игровое время (опорные точки), последний контакт с центром, станции. От них считаются экраны входа, загрузки и приветствия.
Логика времени в machines/world/chrono.py, здесь обёртка."""
import datetime as dt

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from machines.models import Machine, TimeAnchor, World
from machines.world import chrono

router = Router(tags=["world"])


class WorldOut(Schema):
    core_last_contact: dt.date
    beacon_last_sync: dt.date
    cert_not_after: dt.date
    stations_known: int
    stations_reachable: int
    audit_per_day: int


def _out(world):
    return WorldOut(**{name: getattr(world, name) for name in WorldOut.model_fields})


@router.get("", response=WorldOut)
def read(request):
    return _out(World.current())


@router.put("", response=WorldOut)
def save(request, body: WorldOut):
    world = World.current()
    for name in WorldOut.model_fields:
        setattr(world, name, getattr(body, name))
    world.full_clean()
    world.save()
    return _out(world)


# ---------- игровое время ----------

class AnchorOut(Schema):
    id: int
    real_at: dt.datetime
    game_at: dt.datetime
    rate: float
    note: str
    past: bool              # наступила: не правится
    current: bool           # действует сейчас


class ZoneRow(Schema):
    zone: str
    machines: list[str]         # хосты машин в этом поясе


class TimeOut(Schema):
    real_now: dt.datetime
    game_now: dt.datetime
    rate: float
    anchors: list[AnchorOut]
    zones: list[ZoneRow]


class AnchorIn(Schema):
    real_at: dt.datetime | None = None      # None: сейчас
    game_at: dt.datetime
    rate: float = 1
    note: str = ""


class TimeWarnings(Schema):
    game_before: dt.datetime                # каким было бы игровое время в этот момент без новой точки
    items: list[str]


def _time():
    now = timezone.now()
    rows = list(TimeAnchor.objects.order_by("real_at", "pk"))
    current = chrono.anchor_at(now).pk
    zones = {}
    for host, name, zone in Machine.objects.order_by("hostname", "name").values_list("hostname", "name", "time_zone"):
        zones.setdefault(zone or "UTC", []).append(host or name)
    return TimeOut(real_now=now, game_now=chrono.to_game(now), rate=chrono.rate_now(),
                   zones=[ZoneRow(zone=zone, machines=hosts) for zone, hosts in sorted(zones.items(), key=lambda pair: (pair[0] != "UTC", pair[0]))], anchors=[
        AnchorOut(id=row.pk, real_at=row.real_at, game_at=row.game_at, rate=float(row.rate), note=row.note, past=row.real_at <= now, current=row.pk == current)
        for row in rows
    ])


@router.get("/time", response=TimeOut)
def time(request):
    return _time()


@router.post("/time", response=TimeOut)
def add_anchor(request, body: AnchorIn):
    try:
        chrono.add(body.real_at, body.game_at, body.rate, body.note)
    except chrono.TimeError as error:
        raise HttpError(400, str(error))
    return _time()


@router.put("/time/{int:anchor_id}", response=TimeOut)
def change_anchor(request, anchor_id: int, body: AnchorIn):
    try:
        chrono.change(get_object_or_404(TimeAnchor, pk=anchor_id), body.real_at or timezone.now(), body.game_at, body.rate, body.note)
    except chrono.TimeError as error:
        raise HttpError(400, str(error))
    return _time()


@router.delete("/time/{int:anchor_id}", response=TimeOut)
def remove_anchor(request, anchor_id: int):
    try:
        chrono.remove(get_object_or_404(TimeAnchor, pk=anchor_id))
    except chrono.TimeError as error:
        raise HttpError(400, str(error))
    return _time()


@router.post("/time/check", response=TimeWarnings)
def check_anchor(request, body: AnchorIn, skip: int | None = None):
    """Что заметит мир от такой точки: сдвиг назад и записи, которые окажутся «в будущем». Ничего не сохраняет."""
    real_at = max(body.real_at or timezone.now(), timezone.now())
    return TimeWarnings(game_before=chrono.game_before(real_at, skip), items=chrono.warnings(real_at, body.game_at, skip=skip))
