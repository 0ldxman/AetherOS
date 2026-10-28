"""Группы машины и привилегии записи.

Группы типа системы действуют на всех его машинах; у машины одноимённая группа заменяет группу типа, а отключённая прячет её.
Пока ни у типа, ни у машины групп нет совсем, действуют DEFAULT_GROUPS (как места: умолчание в коде).
"""
from machines.models import Group, SystemType
from machines.privileges import DEFAULT_GROUPS, PRIVILEGES, Principal


def effective(machine):
    """{имя: (привилегии, все записи)} групп, действующих на машине."""
    system = SystemType.objects.filter(code=machine.system).first()
    found = {}
    rows = list(Group.objects.filter(system_type=system)) if system else []
    rows += list(Group.objects.filter(machine=machine))
    if not rows:
        return {name: (frozenset(spec["privileges"]), spec["everyone"]) for name, spec in DEFAULT_GROUPS.items()}
    for row in rows:                                                     # группы машины идут после групп типа и заменяют их
        if row.disabled:
            found.pop(row.name, None)
        else:
            found[row.name] = (frozenset(row.privileges), row.everyone)
    return found


def principal_for(profile):
    """Principal записи: группы по имени (существующие на машине) и «все записи»."""
    available = effective(profile.machine)
    groups = {name for name in profile.groups if name in available} | {name for name, (_, everyone) in available.items() if everyone}
    privileges = set().union(*(available[name][0] for name in groups)) if groups else set()
    return Principal(profile.login, frozenset(groups), frozenset(privileges), bool(profile.root))


def choices(machine):
    """Имена групп машины для админки."""
    return sorted(effective(machine))


__all__ = ["PRIVILEGES", "choices", "effective", "principal_for"]
