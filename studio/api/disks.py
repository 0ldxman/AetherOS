"""Диски машины: монтирования (том локально или путь хоста по сети), экспорты и дерево файлов «глазами учётки».

Дерево собирает вид машины (filesystem.machine_view) с правами выбранной учётки: что ей видно, что можно прочитать, где права,
слои защиты и условия по ключам. Ничего не меняется: это взгляд автора, а не вход игрока.
"""

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from filesystem import rights
from filesystem.machine_view import MachineView
from filesystem.models import Volume
from machines.access.groups import principal_for
from machines.models import Export, Machine, MachineMount, MachineProfile

router = Router(tags=["disks"])


class Ref(Schema):
    id: int
    label: str


class DiskMount(Schema):
    id: int
    mode: str
    volume: Ref | None
    volume_path: str
    host: Ref | None
    host_path: str
    account: Ref | None
    mount_path: str
    order: int


class ExportRow(Schema):
    id: int
    path: str


class Host(Schema):
    id: int
    label: str
    accounts: list[Ref]
    exports: list[str]


class Disks(Schema):
    mounts: list[DiskMount]
    exports: list[ExportRow]
    volumes: list[Ref]
    hosts: list[Host]


class MountIn(Schema):
    mode: str = "local"
    volume: int | None = None
    volume_path: str = ""
    host: int | None = None
    host_path: str = ""
    account: int | None = None
    mount_path: str = ""
    order: int = 0


class ExportIn(Schema):
    path: str


class TreeNode(Schema):
    name: str
    path: str
    is_dir: bool
    owner: str
    group: str
    mode: str
    readable: bool
    hidden: bool
    layers: bool
    keys: bool
    format: str
    mount: str             # точка монтирования, если это она


class Listing(Schema):
    path: str
    readable: bool
    denied: str
    nodes: list[TreeNode]


def _ref(obj, label):
    return Ref(id=obj.pk, label=label) if obj is not None else None


def _disks(machine):
    mounts = machine.mounts.select_related("volume", "host", "account").order_by("mount_path", "order", "id")
    return Disks(
        mounts=[
            DiskMount(id=m.pk, mode=m.mode, volume=_ref(m.volume, m.volume.name or m.volume.slug if m.volume_id else ""), volume_path=m.volume_path,
                  host=_ref(m.host, m.host.label if m.host_id else ""), host_path=m.host_path,
                  account=_ref(m.account, m.account.login if m.account_id else ""), mount_path=m.mount_path, order=m.order)
            for m in mounts
        ],
        exports=[ExportRow(id=e.pk, path=e.path) for e in machine.exports.all()],
        volumes=[Ref(id=v.pk, label=f"{v.name or v.slug} ({v.slug})") for v in Volume.objects.order_by("slug")],
        hosts=[
            Host(id=h.pk, label=h.label, accounts=[Ref(id=p.pk, label=p.login) for p in h.profiles.all()],
                 exports=[e.path for e in h.exports.all()])
            for h in Machine.objects.exclude(pk=machine.pk).prefetch_related("profiles", "exports").order_by("hostname")
        ],
    )


@router.get("/{int:machine_id}/disks", response=Disks)
def disks(request, machine_id: int):
    return _disks(get_object_or_404(Machine, pk=machine_id))


def _apply(mount, body):
    for name in ("mode", "volume_path", "host_path", "mount_path", "order"):
        setattr(mount, name, getattr(body, name))
    mount.volume_id = body.volume if body.mode == MachineMount.Mode.LOCAL else None
    mount.host_id = body.host if body.mode == MachineMount.Mode.REMOTE else None
    mount.account_id = body.account if body.mode == MachineMount.Mode.REMOTE else None
    mount.full_clean()
    mount.save()


@router.post("/{int:machine_id}/mounts", response=Disks)
def new_mount(request, machine_id: int, body: MountIn):
    machine = get_object_or_404(Machine, pk=machine_id)
    _apply(MachineMount(machine=machine), body)
    return _disks(machine)


@router.put("/{int:machine_id}/mounts/{int:mount_id}", response=Disks)
def save_mount(request, machine_id: int, mount_id: int, body: MountIn):
    mount = get_object_or_404(MachineMount, pk=mount_id, machine_id=machine_id)
    _apply(mount, body)
    return _disks(mount.machine)


@router.delete("/{int:machine_id}/mounts/{int:mount_id}", response=Disks)
def drop_mount(request, machine_id: int, mount_id: int):
    get_object_or_404(MachineMount, pk=mount_id, machine_id=machine_id).delete()
    return _disks(get_object_or_404(Machine, pk=machine_id))


@router.post("/{int:machine_id}/exports", response=Disks)
def new_export(request, machine_id: int, body: ExportIn):
    machine = get_object_or_404(Machine, pk=machine_id)
    export = Export(machine=machine, path=body.path)
    export.save()
    return _disks(machine)


@router.delete("/{int:machine_id}/exports/{int:export_id}", response=Disks)
def drop_export(request, machine_id: int, export_id: int):
    get_object_or_404(Export, pk=export_id, machine_id=machine_id).delete()
    return _disks(get_object_or_404(Machine, pk=machine_id))


@router.get("/{int:machine_id}/tree", response=Listing)
def tree(request, machine_id: int, account: int, path: str = "/"):
    """Содержимое папки так, как его видит учётка: права, слои, ключи. Сеть идёт через хосты, как у игрока."""
    machine = get_object_or_404(Machine, pk=machine_id)
    profile = get_object_or_404(MachineProfile, pk=account, machine=machine)
    principal = principal_for(profile)
    view = MachineView(machine, None, principal)
    path = "/" + "/".join(part for part in path.split("/") if part)
    try:
        rights.check(view, principal, path, "r")
        readable, denied = True, ""
    except rights.Denied as refused:
        readable, denied = False, refused.path
    points = {layer.point for layer in view.layers}
    nodes = []
    for entry in view.children(path) if readable else []:
        owner, group, mode = rights.rights_at(view, entry.path, entry)
        try:
            rights.check(view, principal, entry.path, "r")
            can = True
        except rights.Denied:
            can = False
        nodes.append(TreeNode(
            name=entry.name, path=entry.path, is_dir=entry.is_dir, owner=owner, group=group, mode=mode, readable=can, hidden=entry.hidden,
            layers=bool(entry.state.strip()), keys=bool(entry.conditions), format=entry.item.format if entry.item is not None else "",
            mount=entry.path if entry.path in points else "",
        ))
    return Listing(path=path, readable=readable, denied=denied, nodes=nodes)


