"""Теги и счётчики: одно хранилище для мира, игрока, персонажа, машины, сервера, объекта и учётки (общей для всех на ней).

Значение бывает общим (user пусто) или своим у каждого игрока (user — игрок): «этот персонаж доверяет этому игроку на 3».
У владельца «игрок» значения и так его собственные: owner_id — сам игрок, user пусто.
Тег — то же число: 1 стоит, 0 снят. Вещь хранится номером (pk), поэтому переименование хоста или кода её не теряет.
Описание (подпись, подписи значений) — необязательная таблица ValueInfo; без него значение просто число.
"""
import re

from django.db import transaction
from django.utils import timezone

from machines import memo

TAG, COUNT = "tag", "count"
WORLD, PLAYER = "world", "player"
OWNERS = {WORLD: "мир", PLAYER: "игрок", "character": "персонаж", "machine": "машина", "server": "сервер", "object": "объект",
          "account": "учётка"}
NAME = re.compile(r"^[\w][\w.-]{0,63}$")


class BadValue(ValueError):
    pass


def check_name(name):
    name = str(name or "").strip().lower()
    if not NAME.match(name):
        raise BadValue("Имя: буквы, цифры, «.», «-» и «_», до 64 знаков, без пробелов и двоеточий.")
    return name


def _check_owner(owner):
    if owner not in OWNERS:
        raise BadValue(f"Владелец: {', '.join(OWNERS)}.")
    return owner


# ---------- вещь владельца ----------

def _model(owner):
    if owner == PLAYER:
        from django.contrib.auth import get_user_model

        return get_user_model(), "username"
    if owner == "character":
        from characters.models import Character

        return Character, "code"
    if owner == "machine":
        from machines.models import Machine

        return Machine, "hostname"
    if owner == "server":
        from machines.models import NetResource

        return NetResource, "address"
    if owner == "object":
        from filesystem.models import Item

        return Item, "slug"
    return None, ""


def owner_id(owner, thing):
    """Номер вещи владельца: по самой вещи (модель или игрок) или по её ключу (логин, код, хост, адрес, слаг). Мир — 0, нет вещи — None."""
    _check_owner(owner)
    if owner == WORLD:
        return 0
    if thing is None or thing == "":
        return None
    if hasattr(thing, "pk"):
        return thing.pk
    if owner == "account":                                   # учётка по ключу «логин@хост»
        from machines.world import edits

        found = edits.account(str(thing))
        return found.pk if found is not None else None
    model, field = _model(owner)
    return model.objects.filter(**{f"{field}__iexact": str(thing).strip()}).values_list("pk", flat=True).first()


def owner_key(owner, pk):
    """Ключ вещи по номеру (для подписей и условий)."""
    if owner == WORLD:
        return ""
    if owner == "account":
        from machines.models import MachineProfile
        from machines.world import edits

        return edits.account_key(MachineProfile.objects.select_related("machine").filter(pk=pk).first()) or str(pk)
    model, field = _model(owner)
    return model.objects.filter(pk=pk).values_list(field, flat=True).first() or str(pk)


THING_FIELDS = {"character": "character", "machine": "machine", "server": "server", "object": "item", PLAYER: "who", "account": "account"}


def _user(who):
    if hasattr(who, "pk"):
        return who
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(username__iexact=str(who).strip()).first()


def target(data, player=None):
    """(владелец, номер вещи, игрок или None) по полям ноды или действия: owner, вещь (character, machine, server, item, who),
    scope «player» — своё у игрока for (пусто — игрок хода player). Нет вещи или игрока — BadValue."""
    owner = _check_owner(data.get("owner") or WORLD)
    oid = 0
    if owner != WORLD:
        thing = data.get(THING_FIELDS[owner])
        if owner == PLAYER and thing in (None, ""):
            thing = player
        oid = owner_id(owner, thing)
        if oid is None:
            raise BadValue(f"нет вещи: {OWNERS[owner]} {thing if isinstance(thing, str) else ''}".strip())
    user = None
    if owner not in (WORLD, PLAYER) and data.get("scope") == "player":
        who = data.get("for")
        user = _user(who) if who not in (None, "") else player
        if user is None:
            raise BadValue("нет игрока: значение «для игрока»")
    return owner, oid, user


# ---------- чтение ----------

def _rows(owner, oid, user_id):
    from engine.models import Value

    found = Value.objects.filter(owner=owner, owner_id=oid, user_id=user_id).values_list("kind", "name", "value")
    return {(kind, name): value for kind, name, value in found}


def _cached(owner, oid, user):
    user_id = getattr(user, "pk", user)
    return memo.cached(("values", owner, oid, user_id), lambda: _rows(owner, oid, user_id))


def _forget(owner, oid, user):
    memo.forget(("values", owner, oid, getattr(user, "pk", user)))


def get(kind, owner, oid, name, user=None):
    """Значение тега (0/1) или счётчика; нет вещи или записи — 0."""
    if oid is None:
        return 0
    return _cached(owner, oid, user).get((kind, name), 0)


def on(owner, oid, name, user=None):
    return bool(get(TAG, owner, oid, name, user))


def names(kind, owner, oid, user=None, lit=True):
    """Имена тегов (стоящих, если lit) или счётчиков владельца."""
    if oid is None:
        return set()
    return {name for (k, name), value in _cached(owner, oid, user).items() if k == kind and (value or not lit or kind == COUNT)}


# ---------- изменения ----------

def _who(source, actor):
    from world.state import _who as who

    return who(source, actor)[:200]


def _after(kind, owner, oid, name, user, value, old, source, actor, depth):
    """Журнал, события и триггеры мира после изменения."""
    _forget(owner, oid, user)
    from engine.events import emit

    who = user if user is not None else (_player(oid) if owner == PLAYER else actor)
    shared = user is None and owner != PLAYER                    # общее значение: будит ждущих у всех
    common = {"source": source, "owner": owner, "thing": owner_key(owner, oid), "key": name, "per": user is not None, "shared": shared}
    if kind == TAG:
        emit("value.tag", who, on=bool(value), **common)
    else:
        emit("value.count", who, value=value, delta=value - old, **common)

    if owner == WORLD:
        from world import state

        if kind == TAG:
            state._log("flag", name, f"метка world:{name} {'поставлена' if value else 'снята'}", source, actor)
            emit("world.flag", actor, source=source, flag=name, on=bool(value))
        else:
            state._log("counter", name, f"world:{name} {value - old:+d} → {value}", state._who(source, actor), actor)
            emit("world.counter", actor, source=source, counter=name, delta=value - old, value=value)
    elif owner == PLAYER:
        player = who
        if kind == TAG:
            emit("flag.set" if value else "flag.unset", player, source=source, flag=name)
        else:
            emit("player.counter", player, source=source, counter=name, value=value)
    if user is None and owner != PLAYER:
        from world import state

        state.forget()
        state.evaluate(depth)


def _player(pk):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(pk=pk).first()


def _write(kind, owner, oid, name, user, compute, source, actor):
    from engine.models import Value

    _check_owner(owner)
    if oid is None:
        raise BadValue(f"нет такой вещи: {OWNERS[owner]}")
    name = check_name(name)
    user_id = getattr(user, "pk", user)
    with transaction.atomic():
        row, _ = Value.objects.select_for_update().get_or_create(kind=kind, owner=owner, owner_id=oid, user_id=user_id, name=name)
        old = row.value
        new = compute(old)
        if new == old and row.changed_at is not None:
            return name, old, old
        Value.objects.filter(pk=row.pk).update(value=new, changed_at=timezone.now(), changed_by=_who(source, actor))
    return name, old, new


def set_tag(owner, oid, name, lit=True, user=None, source="", actor=None, _depth=0):
    """Поставить или снять тег. Возвращает True, если что-то поменялось."""
    name, old, new = _write(TAG, owner, oid, name, user, lambda _: int(bool(lit)), source, actor)
    if new == old:
        return False
    _after(TAG, owner, oid, name, user, new, old, source, actor, _depth)
    return True


def add(owner, oid, name, delta=1, user=None, source="", actor=None, _depth=0):
    """Прибавить к счётчику. Возвращает новое значение."""
    name, old, new = _write(COUNT, owner, oid, name, user, lambda value: value + int(delta), source, actor)
    if new != old:
        _after(COUNT, owner, oid, name, user, new, old, source, actor, _depth)
    return new


def put(owner, oid, name, value, user=None, source="", actor=None, _depth=0):
    """Задать счётчику значение. Возвращает его."""
    name, old, new = _write(COUNT, owner, oid, name, user, lambda _: int(value), source, actor)
    if new != old:
        _after(COUNT, owner, oid, name, user, new, old, source, actor, _depth)
    return new


def forget(kind, owner, oid, name, user=None):
    """Убрать значение совсем (пульт мира: удалить метку или счётчик)."""
    from engine.models import Value

    Value.objects.filter(kind=kind, owner=owner, owner_id=oid, user_id=getattr(user, "pk", user), name=name).delete()
    _forget(owner, oid, user)


# ---------- описание ----------

def info(kind, owner, name, oid=0):
    """(подпись, подписи значений) значения: своё описание вещи, иначе общее для этого вида владельца."""
    from engine.models import ValueInfo

    rows = {row.owner_id: row for row in ValueInfo.objects.filter(kind=kind, owner=owner, name=name, owner_id__in={0, oid or 0})}
    row = rows.get(oid or 0) or rows.get(0)
    return (row.label, dict(row.labels or {})) if row else ("", {})


def describe(kind, owner, name, label=None, labels=None, oid=0):
    from engine.models import ValueInfo

    row, _ = ValueInfo.objects.get_or_create(kind=kind, owner=owner, owner_id=oid or 0, name=check_name(name))
    if label is not None:
        row.label = label.strip()[:200]
    if labels is not None:
        row.labels = {str(int(k)): str(v).strip()[:80] for k, v in labels.items() if str(k).lstrip("-").isdigit() and str(v).strip()}
    row.save()
    return row


def caption(kind, owner, oid, name, value):
    """Подпись значения счётчика («Архив» для 2) или пусто."""
    return info(kind, owner, name, oid)[1].get(str(value), "")
