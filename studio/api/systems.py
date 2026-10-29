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
from filesystem.models import Volume
from machines.models import EntryPolicy, Group, Machine, Place, SystemType, SystemVolume
from machines.world.facts import facts
from machines.world.identity import identity_of
from machines.world.places import DEFAULTS
from scenes import markup
from terminal.scenes.shell import GREETING_PARAMS, greeting_params
from studio.api.disks import Ref
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


class ImageRow(Schema):
    id: int
    volume: Ref
    volume_path: str
    mount_path: str
    order: int


class ImageIn(Schema):
    volume: int
    volume_path: str = ""
    mount_path: str
    order: int = 0


class GreetingParam(Schema):
    name: str
    label: str


class GreetingPart(Schema):
    text: str
    style: str | None


class GreetingError(Schema):
    line: int
    text: str


class GreetingPreview(Schema):
    lines: list[list[GreetingPart]]
    errors: list[GreetingError]
    machine: str | None         # на какой машине посчитаны значения


class GreetingIn(Schema):
    greeting: str


class SystemOut(Schema):
    code: str
    greeting: str
    greeting_params: list[GreetingParam]
    name: str
    path_style: str
    entry_policy: int | None
    machines: list[str]
    places: list[PlaceRow]
    privileges: list[Privilege]
    groups: list[TypeGroup]
    policies: list[Policy]
    image: list[ImageRow]
    volumes: list[Ref]


class SystemIn(Schema):
    code: str | None = None     # пусто или тот же: код не меняется
    greeting: str = ""
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
        code=system.code, name=system.name, greeting=system.greeting,
        greeting_params=[GreetingParam(name=name, label=label) for name, label in GREETING_PARAMS.items()],
        path_style=system.path_style, entry_policy=system.entry_policy_id,
        machines=list(Machine.objects.filter(system=system.code).order_by("hostname").values_list("hostname", flat=True)),
        places=[PlaceRow(name=name, path=own.get(name, ""), default=DEFAULTS.get(name, ""), machines=sorted(overridden.get(name, [])))
                for name in names],
        privileges=[Privilege(code=code, label=label) for code, label in PRIVILEGES.items()],
        groups=[TypeGroup(**row) for row in groups.type_table(system)],
        policies=[Policy(id=p.pk, name=p.name) for p in EntryPolicy.objects.order_by("name")],
        image=[
            ImageRow(id=row.pk, volume=Ref(id=row.volume_id, label=row.volume.name or row.volume.slug), volume_path=row.volume_path,
                     mount_path=row.mount_path, order=row.order)
            for row in system.volumes.select_related("volume")
        ],
        volumes=[Ref(id=v.pk, label=f"{v.name or v.slug} ({v.slug})") for v in Volume.objects.order_by("slug")],
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
    system.greeting = body.greeting
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


def _image_row(system, body, row=None):
    row = row or SystemVolume(system_type=system)
    row.volume_id, row.volume_path, row.mount_path, row.order = body.volume, body.volume_path, body.mount_path, body.order
    row.full_clean()
    row.save()


@router.post("/{code}/image", response=SystemOut)
def add_image(request, code: str, body: ImageIn):
    system = _system(code)
    _image_row(system, body)
    return _out(system)


@router.put("/{code}/image/{int:row_id}", response=SystemOut)
def save_image(request, code: str, row_id: int, body: ImageIn):
    system = _system(code)
    _image_row(system, body, get_object_or_404(SystemVolume, pk=row_id, system_type=system))
    return _out(system)


@router.delete("/{code}/image/{int:row_id}", response=SystemOut)
def drop_image(request, code: str, row_id: int):
    system = _system(code)
    get_object_or_404(SystemVolume, pk=row_id, system_type=system).delete()
    return _out(system)


@router.post("/{code}/greeting/preview", response=GreetingPreview)
def preview_greeting(request, code: str, body: GreetingIn):
    """Как приветствие выглядит у игрока: значения берутся с первой машины ОС (или с запасных значений, если машин нет)."""
    system = _system(code)
    machine = Machine.objects.filter(system=system.code).order_by("hostname").first()
    host = machine.hostname if machine else "host"
    params = greeting_params(identity_of(host), "player", None, system, facts(machine) if machine else None)
    lines, errors = [], []
    for number, line in enumerate(body.greeting.splitlines(), 1):
        parts, found = markup.parse_line(line, params)
        lines.append([GreetingPart(text=text, style=style) for text, style in parts])
        errors += [GreetingError(line=number, text=text) for text in found]
    return GreetingPreview(lines=lines, errors=errors, machine=machine.hostname if machine else None)
