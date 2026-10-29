"""Группы машины и привилегии записи.

Группы типа системы действуют на всех его машинах; у машины одноимённая группа заменяет группу типа, а отключённая прячет её.
Пока ни у типа, ни у машины групп нет совсем, действуют DEFAULT_GROUPS (как места: умолчание в коде).
"""
from django.db.models import Q

from machines import memo
from machines.models import Group
from machines.access.privileges import DEFAULT_GROUPS, PRIVILEGES, Principal


def effective(machine):
    """{имя: (привилегии, все записи)} групп, действующих на машине."""
    return memo.cached(("groups", machine.pk, machine.system), lambda: _load(machine))


def _load(machine):
    found = {}
    rows = list(Group.objects.filter(Q(system_type__code=machine.system) | Q(machine=machine)).order_by("machine_id"))
    rows.sort(key=lambda row: row.machine_id is not None)                # группы машины идут после групп типа и заменяют их
    if not rows:
        return {name: (frozenset(spec["privileges"]), spec["everyone"]) for name, spec in DEFAULT_GROUPS.items()}
    for row in rows:
        if row.disabled:
            found.pop(row.name, None)
        else:
            found[row.name] = (frozenset(row.privileges), row.everyone)
    return found


def make_explicit(machine=None, system_type=None):
    """Перед первой своей группой у типа или машины: группы по умолчанию (DEFAULT_GROUPS) записываются явно туда же.

    Умолчание действует, только пока групп нет нигде; без этого первая же своя группа молча отняла бы у записей, например, мосты."""
    if system_type is not None:
        if Group.objects.filter(system_type=system_type).exists():
            return
        if Group.objects.filter(machine__system=system_type.code).exists():
            return                                         # у машин этого типа свои группы: на них умолчание и так не действует
        rows = [Group(system_type=system_type, name=name, **spec) for name, spec in DEFAULT_GROUPS.items()]
    else:
        if Group.objects.filter(Q(system_type__code=machine.system) | Q(machine=machine)).exists():
            return
        rows = [Group(machine=machine, name=name, **spec) for name, spec in DEFAULT_GROUPS.items()]
    Group.objects.bulk_create(rows)


def type_table(system_type):
    """Группы типа системы для автора: [{name, privileges, everyone, source, machines}] (machines: где тип переопределён)."""
    rows = list(Group.objects.filter(system_type=system_type))
    overridden = {}
    for name, host in Group.objects.filter(machine__system=system_type.code).values_list("name", "machine__hostname"):
        overridden.setdefault(name, []).append(host or "")
    if not rows:
        return [{"name": name, "privileges": sorted(spec["privileges"]), "everyone": spec["everyone"], "source": "default",
                 "machines": sorted(overridden.get(name, []))} for name, spec in sorted(DEFAULT_GROUPS.items())]
    return [{"name": row.name, "privileges": sorted(row.privileges), "everyone": row.everyone, "source": "system",
             "machines": sorted(overridden.get(row.name, []))} for row in sorted(rows, key=lambda row: row.name)]


def principal_for(profile):
    """Principal записи: группы по имени (существующие на машине) и «все записи»."""
    available = effective(profile.machine)
    groups = {name for name in profile.groups if name in available} | {name for name, (_, everyone) in available.items() if everyone}
    privileges = set().union(*(available[name][0] for name in groups)) if groups else set()
    return Principal(profile.login, frozenset(groups), frozenset(privileges), bool(profile.root))


def table(machine):
    """Строки групп машины для автора: и действующие, и отключённые на ней группы типа системы.

    [{name, privileges, everyone, source, overrides, disabled, members}]: source это system (группа типа), machine (своя группа
    машины) или default (умолчание из кода, пока своих групп нет нигде); overrides значит, что группа машины заменяет одноимённую
    группу типа; members это логины записей машины в группе."""
    rows = list(Group.objects.filter(Q(system_type__code=machine.system) | Q(machine=machine)))
    system = {row.name: row for row in rows if row.machine_id is None}
    own = {row.name: row for row in rows if row.machine_id is not None}
    profiles = list(machine.profiles.values_list("login", "groups"))
    found = []
    if not rows:
        source = {name: ("default", spec["privileges"], spec["everyone"], False) for name, spec in DEFAULT_GROUPS.items()}
    else:
        source = {name: ("system", row.privileges, row.everyone, False) for name, row in system.items()}
        for name, row in own.items():
            if row.disabled:
                base = system.get(name)
                source[name] = ("system", base.privileges if base else [], base.everyone if base else False, True)
            else:
                source[name] = ("machine", row.privileges, row.everyone, False)
    for name, (kind, privileges, everyone, disabled) in sorted(source.items()):
        members = [] if disabled else [login for login, names in profiles if everyone or name in (names or [])]
        found.append({
            "name": name, "privileges": sorted(privileges), "everyone": everyone, "source": kind, "disabled": disabled,
            "overrides": kind == "machine" and name in system, "members": sorted(members),
        })
    return found


def choices(machine):
    """Имена групп машины для админки."""
    return sorted(effective(machine))


__all__ = ["PRIVILEGES", "choices", "effective", "principal_for"]
