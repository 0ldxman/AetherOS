"""Тома: список, дерево тома и действия над ним (filesystem.manager.filemanager, как у файлового менеджера админки)."""
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from filesystem.manager import filemanager
from filesystem.models import Placement, Volume
from machines.world.create import create_volume
from studio.api.protection import Dump, Layer, Problem

router = Router(tags=["volumes"])


class Mount(Schema):
    machine: str
    path: str


class VolumeRow(Schema):
    id: int
    slug: str
    name: str
    label: str
    files: int
    folders: int
    mounts: list[Mount]


class ItemBrief(Schema):
    id: int
    slug: str
    name: str
    format: str
    size: int | None
    used: int


class Node(Schema):
    id: int
    parent: int | None
    kind: str
    name: str
    hidden: bool
    system: bool
    owner: str
    group: str
    mode: str
    access: str
    state: str
    item: ItemBrief | None


class VolumeTree(Schema):
    id: int
    slug: str
    name: str
    label: str
    uuid: str
    rows: list[Node]


class NewFolder(Schema):
    parent: int | None = None
    name: str


class NewFile(Schema):
    parent: int | None = None
    name: str
    format: str = ""


class Link(Schema):
    parent: int | None = None
    item: int
    name: str = ""


class Change(Schema):
    name: str | None = None
    hidden: bool | None = None
    system: bool | None = None
    owner: str | None = None
    group: str | None = None
    mode: str | None = None


class Selection(Schema):
    ids: list[int]
    parent: int | None = None


class Created(Schema):
    item: int | None = None


class Done(Schema):
    count: int


def _mounts(volume):
    return [Mount(machine=mount.machine.hostname, path=mount.mount_path or "") for mount in volume.mounts.all()]


@router.get("", response=list[VolumeRow])
def volumes(request):
    found = (
        Volume.objects.order_by("slug").prefetch_related("mounts__machine")
        .annotate(
            files=Count("placements", filter=Q(placements__kind=Placement.Kind.ITEM)),
            folders=Count("placements", filter=Q(placements__kind=Placement.Kind.FOLDER)),
        )
    )
    return [
        VolumeRow(id=v.pk, slug=v.slug, name=v.name, label=v.label, files=v.files, folders=v.folders, mounts=_mounts(v))
        for v in found
    ]


class NewVolume(Schema):
    slug: str
    name: str = ""
    label: str = ""
    uuid: str = ""              # пусто: сгенерируется
    template: int | None = None
    machine: int | None = None  # сразу смонтировать на машину
    mount_path: str = ""


class VolumeMade(Schema):
    id: int


@router.post("", response=VolumeMade)
def create(request, body: NewVolume):
    """Новый том (пустой или по шаблону файловой структуры), по желанию сразу смонтированный на машину."""
    disk = create_volume(body.slug, body.name, body.label, body.uuid or None, body.template, body.machine, body.mount_path)
    return VolumeMade(id=disk.pk)


@router.get("/{int:volume_id}", response=VolumeTree)
def tree(request, volume_id: int):
    volume = get_object_or_404(Volume, pk=volume_id)
    return VolumeTree(
        id=volume.pk, slug=volume.slug, name=volume.name, label=volume.label, uuid=str(volume.uuid),
        rows=filemanager.data(volume)["rows"],
    )


@router.post("/{int:volume_id}/folders")
def new_folder(request, volume_id: int, body: NewFolder):
    filemanager.new_folder(get_object_or_404(Volume, pk=volume_id), body.parent, body.name)
    return {}


@router.post("/{int:volume_id}/files", response=Created)
def new_file(request, volume_id: int, body: NewFile):
    placement = filemanager.new_file(get_object_or_404(Volume, pk=volume_id), body.parent, body.name, body.format)
    return Created(item=placement.item_id)


@router.post("/{int:volume_id}/links")
def link(request, volume_id: int, body: Link):
    filemanager.link(get_object_or_404(Volume, pk=volume_id), body.parent, body.item, body.name)
    return {}


@router.patch("/{int:volume_id}/placements/{int:placement_id}")
@transaction.atomic
def change(request, volume_id: int, placement_id: int, body: Change):
    volume = get_object_or_404(Volume, pk=volume_id)
    if body.name is not None:
        filemanager.rename(volume, placement_id, body.name)
    flags = {key: value for key, value in (("hidden", body.hidden), ("system", body.system)) if value is not None}
    if flags:
        filemanager.set_flags(volume, placement_id, **flags)
    if any(value is not None for value in (body.owner, body.group, body.mode)):
        current = get_object_or_404(Placement, pk=placement_id, volume=volume)
        filemanager.set_rights(
            volume, placement_id,
            current.owner if body.owner is None else body.owner,
            current.group if body.group is None else body.group,
            current.mode if body.mode is None else body.mode,
        )
    return {}


@router.post("/{int:volume_id}/delete", response=Done)
def delete(request, volume_id: int, body: Selection):
    return Done(count=filemanager.delete(get_object_or_404(Volume, pk=volume_id), body.ids))


@router.post("/{int:volume_id}/move", response=Done)
def move(request, volume_id: int, body: Selection):
    return Done(count=filemanager.move(get_object_or_404(Volume, pk=volume_id), body.ids, body.parent))


@router.post("/{int:volume_id}/copy", response=Done)
def copy(request, volume_id: int, body: Selection):
    return Done(count=filemanager.copy(get_object_or_404(Volume, pk=volume_id), body.ids, body.parent))


# ---- файл со своим текстом (без объекта) -----------------------------------------------------------------------------

class NewText(Schema):
    parent: int | None = None
    name: str
    content: str = ""


class TextFile(Schema):
    id: int
    volume: int
    volume_name: str
    parent: int | None
    name: str
    path: str
    format: str
    content: str
    access: str
    state: str


class TextIn(Schema):
    content: str = ""
    access: str = ""
    state: str = ""


class TextPreview(Schema):
    layers: list[Layer]
    problems: list[Problem]
    access_error: str
    keys: list[str]
    unknown_keys: list[str]
    plain: Dump | None
    layered: Dump | None


class Converted(Schema):
    item: int


def _text_file(volume_id, placement_id):
    return get_object_or_404(Placement.objects.select_related("volume"), pk=placement_id, volume_id=volume_id, kind=Placement.Kind.FILE)


def _text_out(placement):
    from secure.access import format_condition

    from filesystem.machine_view.entries import FILE, Entry

    return TextFile(
        id=placement.pk, volume=placement.volume_id, volume_name=placement.volume.name or placement.volume.slug, parent=placement.parent_id,
        name=placement.name, path=placement.path(), format=Entry(path=f"/{placement.name}", kind=FILE).format, content=placement.content,
        access=format_condition(placement.access) if placement.access else "", state=placement.state,
    )


@router.post("/{int:volume_id}/text-files", response=TextFile)
def new_text(request, volume_id: int, body: NewText):
    placement = filemanager.new_text_file(get_object_or_404(Volume, pk=volume_id), body.parent, body.name, body.content)
    return _text_out(placement)


@router.get("/{int:volume_id}/text-files/{int:placement_id}", response=TextFile)
def read_text(request, volume_id: int, placement_id: int):
    return _text_out(_text_file(volume_id, placement_id))


@router.put("/{int:volume_id}/text-files/{int:placement_id}", response=TextFile)
def save_text(request, volume_id: int, placement_id: int, body: TextIn):
    """Текст, условие и слои файла: защита у такого файла своя (у места), объекта над ним нет."""
    from django.core.exceptions import ValidationError

    from documents.markup.expr import SpoilerSyntaxError, parse_expr

    placement = _text_file(volume_id, placement_id)
    errors = {}
    placement.content = body.content
    try:
        placement.access = parse_expr(body.access) if body.access.strip() else {}
    except SpoilerSyntaxError as exc:
        errors["access"] = [str(exc)]
    placement.state = body.state
    placement.access_mode = placement.state_mode = Placement.Mode.INHERIT
    try:
        from filesystem.layers.validators import validate_state_text

        validate_state_text(body.state)
    except ValidationError as exc:
        errors["state"] = exc.messages
    if errors:
        raise ValidationError(errors)
    placement.full_clean()
    placement.save()
    return _text_out(placement)


@router.post("/{int:volume_id}/text-files/{int:placement_id}/preview", response=TextPreview)
def preview_text(request, volume_id: int, placement_id: int, body: TextIn):
    """Что игрок получит из этого файла (байты со слоями и без) и разбор слоёв и условия, ничего не сохраняя."""
    from filesystem.machine_view.entries import FILE, Entry
    from studio.api.protection import check_protection, entry_dump

    placement = _text_file(volume_id, placement_id)
    layers, problems, access_error, slugs, unknown = check_protection(body.state, body.access)
    placement.content = body.content

    def dump(state):
        placement.state = state
        found = entry_dump(Entry(path=f"/{placement.name}", kind=FILE, placement=placement, text=body.content))
        return found

    return TextPreview(
        layers=layers, problems=problems, access_error=access_error,
        keys=slugs, unknown_keys=unknown, plain=dump(""), layered=dump(body.state) if body.state.strip() and not problems else None,
    )


@router.post("/{int:volume_id}/text-files/{int:placement_id}/to-item", response=Converted)
def to_item(request, volume_id: int, placement_id: int):
    """Сделать объектом: текст, условие и слои переезжают в новый объект."""
    return Converted(item=filemanager.to_item(_text_file(volume_id, placement_id), request.user).pk)
