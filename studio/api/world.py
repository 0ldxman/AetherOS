"""Настройки мира: «сейчас» в игре, последний контакт с центром, станции. От них считаются экраны входа, загрузки и приветствия."""
import datetime as dt

from ninja import Router, Schema

from machines.models import World

router = Router(tags=["world"])


class WorldOut(Schema):
    game_now: dt.datetime
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
