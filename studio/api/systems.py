"""ОС (SystemType): свойства, системные пути (места) и группы ОС.

Код ОС выбирает сцены и команды в Python. Его можно сменить: машины с этим кодом переезжают на новый (Machine.system — строка).
Но если в движке под новый код нет сцен, машины получат поведение по умолчанию. Места и группы ОС действуют на всех его
машинах, машина может переопределить их своими (вкладка «Группы» машины). Умолчания движка (machines.world.places.DEFAULTS и
machines.access.privileges.DEFAULT_GROUPS) показываются, пока у типа своих значений нет.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from machines.access import groups
from machines.access.privileges import PRIVILEGES
from machines.models import EntryPolicy, Group, Machine, Place, SystemType
from machines.world.places import DEFAULTS
from studio.api.groups import GroupIn, Privilege
from studio.api.machines import Policy

router = Router(tags=["systems"])


class SystemRow(Schema):
    code: str
    name: str
    path_style: str
    policy: str | None
    machines: int


class PlaceRow(Schema):
    name: str
    path: str               # своё значение типа (пусто: умолчание движка)
    default: str            # умолчание движка (пусто: своего умолчания у имени нет)
    machines: list[str]     # машины, которые это место переопределили


class TypeGroup(Schema):
    name: str
    privileges: list[str]
    everyone: bool
    source: str             # system | default
    machines: list[str]


class SystemOut(Schema):
    code: str
    name: str
    path_style: str
    entry_policy: int | None
    machines: list[str]
    places: list[PlaceRow]
    privileges: list[Privilege]
    groups: list[TypeGroup]
    policies: list[Policy]


class SystemIn(Schema):
    code: str | None = None     # пусто или тот же: код не меняется
    name: str
    path_style: str = "unix"
    entry_policy: int | None = None


class NewSystem(Schema):
    code: str
    name: str


class PlacesIn(Schema):
    places: dict[str, str]


def _system(code):
    return get_object_or_404(SystemType, code=code)


def _out(system):
    own = {place.name: place.path for place in system.places.all()}
    overridden = {}
    for name, host in Place.objects.filter(machine__system=system.code).values_list("name", "machine__hostname"):
        overridden.setdefault(name, []).append(host or "")
    names = sorted(set(DEFAULTS) | set(own))
    return SystemOut(
        code=system.code, name=system.name, path_style=system.path_style, entry_policy=system.entry_policy_id,
        machines=list(Machine.objects.filter(system=system.code).order_by("hostname").values_list("hostname", flat=True)),
        places=[PlaceRow(name=name, path=own.get(name, ""), default=DEFAULTS.get(name, ""), machines=sorted(overridden.get(name, [])))
                for name in names],
        privileges=[Privilege(code=code, label=label) for code, label in PRIVILEGES.items()],
        groups=[TypeGroup(**row) for row in groups.type_table(system)],
        policies=[Policy(id=p.pk, name=p.name) for p in EntryPolicy.objects.order_by("name")],
    )


@router.get("", response=list[SystemRow])
def systems(request):
    counts = dict(Machine.objects.values_list("system").annotate(n=Count("id")))
    return [
        SystemRow(code=s.code, name=s.name, path_style=s.path_style, policy=s.entry_policy.name if s.entry_policy_id else None,
                  machines=counts.get(s.code, 0))
        for s in SystemType.objects.select_related("entry_policy").order_by("code")
    ]


@router.post("", response=SystemOut)
def create(request, body: NewSystem):
    system = SystemType(code=body.code.strip().upper(), name=body.name.strip() or body.code.strip())
    system.full_clean()
    system.save()
    return _out(system)


@router.get("/{code}", response=SystemOut)
def read(request, code: str):
    return _out(_system(code))


@router.put("/{code}", response=SystemOut)
@transaction.atomic
def save(request, code: str, body: SystemIn):
    system = _system(code)
    new_code = (body.code or code).strip().upper()
    system.code = new_code
    system.name, system.path_style, system.entry_policy_id = body.name, body.path_style, body.entry_policy
    system.full_clean()
    system.save()
    if new_code != code:
        Machine.objects.filter(system=code).update(system=new_code)
    return _out(system)


@router.put("/{code}/places", response=SystemOut)
@transaction.atomic
def places(request, code: str, body: PlacesIn):
    """Места типа целиком: имя -> шаблон пути. Пустой путь значит «как у движка» (своё значение убирается)."""
    system = _system(code)
    errors = {}
    keep = set()
    for name, path in body.places.items():
        name, path = name.strip(), path.strip()
        if not path:
            continue
        place = Place.objects.filter(system_type=system, name=name).first() or Place(system_type=system, name=name)
        place.path = path
        try:
            place.full_clean()
        except ValidationError as exc:
            errors[name] = exc.messages
            continue
        place.save()
        keep.add(name)
    if errors:
        raise ValidationError(errors)
    system.places.exclude(name__in=keep).delete()
    return _out(system)


@router.put("/{code}/groups/{name}", response=SystemOut)
@transaction.atomic
def save_group(request, code: str, name: str, body: GroupIn):
    system = _system(code)
    unknown = [item for item in body.privileges if item not in PRIVILEGES]
    if unknown:
        raise ValidationError({"privileges": [f"Нет таких привилегий: {', '.join(unknown)}."]})
    groups.make_explicit(system_type=system)
    row = Group.objects.filter(system_type=system, name=name).first() or Group(system_type=system, name=name)
    row.privileges, row.everyone = sorted(set(body.privileges)), body.everyone
    row.full_clean()
    row.save()
    return _out(system)


@router.delete("/{code}/groups/{name}", response=SystemOut)
@transaction.atomic
def drop_group(request, code: str, name: str):
    system = _system(code)
    groups.make_explicit(system_type=system)
    Group.objects.filter(system_type=system, name=name).delete()
    return _out(system)
