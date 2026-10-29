"""Тома: список, дерево тома и действия над ним (filesystem.manager.filemanager, как у файлового менеджера админки)."""
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from filesystem.manager import filemanager
from filesystem.models import Placement, Volume

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
