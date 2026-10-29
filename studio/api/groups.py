"""Группы машины: матрица «группы × привилегии» с тем, откуда группа (тип системы или машина), и правка на уровне машины.

Группы типа системы правятся у типа (пока в старой админке); здесь машина может переопределить группу своей, отключить её или
завести новую. Таблицу собирает machines.access.groups.table.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from machines.access import groups
from machines.access.privileges import PRIVILEGES
from machines.models import Group, Machine

router = Router(tags=["groups"])


class Privilege(Schema):
    code: str
    label: str


class GroupRow(Schema):
    name: str
    privileges: list[str]
    everyone: bool
    source: str
    overrides: bool
    disabled: bool
    members: list[str]


class GroupTable(Schema):
    privileges: list[Privilege]
    groups: list[GroupRow]


class GroupIn(Schema):
    privileges: list[str] = []
    everyone: bool = False


def _table(machine):
    return GroupTable(
        privileges=[Privilege(code=code, label=label) for code, label in PRIVILEGES.items()],
        groups=[GroupRow(**row) for row in groups.table(machine)],
    )


@router.get("/{int:machine_id}/groups", response=GroupTable)
def table(request, machine_id: int):
    return _table(get_object_or_404(Machine, pk=machine_id))


@router.put("/{int:machine_id}/groups/{name}", response=GroupTable)
@transaction.atomic
def save(request, machine_id: int, name: str, body: GroupIn):
    """Своя группа машины с этим именем: новая или переопределяющая группу типа."""
    machine = get_object_or_404(Machine, pk=machine_id)
    unknown = [code for code in body.privileges if code not in PRIVILEGES]
    if unknown:
        raise ValidationError({"privileges": [f"Нет таких привилегий: {', '.join(unknown)}."]})
    row = Group.objects.filter(machine=machine, name=name).first() or Group(machine=machine, name=name)
    row.privileges, row.everyone, row.disabled = sorted(set(body.privileges)), body.everyone, False
    row.full_clean()
    row.save()
    return _table(machine)


@router.delete("/{int:machine_id}/groups/{name}", response=GroupTable)
def revert(request, machine_id: int, name: str):
    """Убрать то, что машина сделала с группой: своя группа исчезает, переопределённая или отключённая возвращается к типу."""
    machine = get_object_or_404(Machine, pk=machine_id)
    Group.objects.filter(machine=machine, name=name).delete()
    return _table(machine)


@router.post("/{int:machine_id}/groups/{name}/disable", response=GroupTable)
def disable(request, machine_id: int, name: str):
    """Группа типа системы на этой машине не действует."""
    machine = get_object_or_404(Machine, pk=machine_id)
    Group.objects.update_or_create(machine=machine, name=name, defaults={"disabled": True, "privileges": [], "everyone": False})
    return _table(machine)
