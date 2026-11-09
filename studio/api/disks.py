"""Диски машины: монтирования (диск локально или путь хоста по сети), экспорты и дерево файлов «глазами учётки».

Дерево собирает вид машины (filesystem.machine_view) с правами выбранной учётки: что ей видно, что можно прочитать, где права,
слои защиты и условия по ключам. Ничего не меняется: это взгляд автора, а не вход игрока.
"""

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from filesystem import rights
from filesystem.machine_view import MachineView
from filesystem.manager.overlay import assign_overlay
from filesystem.models import Volume
from machines.access.groups import principal_for
from machines.models import Export, Machine, MachineMount, MachineProfile, SystemVolume

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
    overlay: bool = False     # монтирование диска отличий: меняется выбором «Диск отличий», а не здесь


class ExportRow(Schema):
    id: int
    path: str


class Host(Schema):
    id: int
    label: str
    accounts: list[Ref]
    exports: list[str]


class InheritedMount(Schema):
    volume: Ref
    volume_path: str
    mount_path: str
    order: int


class Disks(Schema):
    inherited: list[InheritedMount]     # образ системного диска ОС машины: лежит под её монтированиями
    mounts: list[DiskMount]
    exports: list[ExportRow]
    volumes: list[Ref]
    overlay: Ref | None                 # диск отличий машины
    overlay_choices: list[Ref]          # какие диски можно назначить отличиями
    hosts: list[Host]


class OverlayIn(Schema):
    volume: int | None = None


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


def _is_overlay(machine, mount):
    return machine.overlay_id is not None and mount.volume_id == machine.overlay_id and mount.mount_path == "/" and mount.volume_path == ""


def _overlay_choices(machine):
    """Диски, которые можно сделать отличиями этой машины: нигде больше не смонтированы, не образ ОС и не отличия другой машины."""
    taken = set(MachineMount.objects.exclude(machine=machine).values_list("volume_id", flat=True))
    taken |= set(SystemVolume.objects.values_list("volume_id", flat=True))
    taken |= set(Machine.objects.exclude(pk=machine.pk).filter(overlay__isnull=False).values_list("overlay_id", flat=True))
    elsewhere = set(machine.mounts.exclude(mount_path="/").values_list("volume_id", flat=True))
    return [v for v in Volume.objects.order_by("slug") if v.pk not in taken and v.pk not in elsewhere]


def _disks(machine):
    mounts = machine.mounts.select_related("volume", "host", "account").order_by("mount_path", "order", "id")
    return Disks(
        inherited=[
            InheritedMount(volume=Ref(id=r.volume_id, label=r.volume.name or r.volume.slug), volume_path=r.volume_path, mount_path=r.mount_path, order=r.order)
            for r in SystemVolume.objects.filter(system_type__code=machine.system).select_related("volume")
        ],
        mounts=[
            DiskMount(id=m.pk, mode=m.mode, volume=_ref(m.volume, m.volume.name or m.volume.slug if m.volume_id else ""), volume_path=m.volume_path,
                  host=_ref(m.host, m.host.label if m.host_id else ""), host_path=m.host_path,
                  account=_ref(m.account, m.account.login if m.account_id else ""), mount_path=m.mount_path, order=m.order, overlay=_is_overlay(machine, m))
            for m in mounts
        ],
        exports=[ExportRow(id=e.pk, path=e.path) for e in machine.exports.all()],
        volumes=[Ref(id=v.pk, label=f"{v.name or v.slug} ({v.slug})") for v in Volume.objects.order_by("slug")],
        overlay=Ref(id=machine.overlay_id, label=f"{machine.overlay.name or machine.overlay.slug} ({machine.overlay.slug})") if machine.overlay_id else None,
        overlay_choices=[Ref(id=v.pk, label=f"{v.name or v.slug} ({v.slug})") for v in _overlay_choices(machine)],
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


OVERLAY_NOTE = "Это диск отличий машины: он выбирается в блоке «Диск отличий» выше."


@router.post("/{int:machine_id}/mounts", response=Disks)
def new_mount(request, machine_id: int, body: MountIn):
    machine = get_object_or_404(Machine, pk=machine_id)
    if body.mode == MachineMount.Mode.LOCAL and machine.overlay_id and body.volume == machine.overlay_id:
        raise ValidationError(OVERLAY_NOTE)
    _apply(MachineMount(machine=machine), body)
    return _disks(machine)


@router.put("/{int:machine_id}/mounts/{int:mount_id}", response=Disks)
def save_mount(request, machine_id: int, mount_id: int, body: MountIn):
    mount = get_object_or_404(MachineMount.objects.select_related("machine"), pk=mount_id, machine_id=machine_id)
    if _is_overlay(mount.machine, mount):
        raise ValidationError(OVERLAY_NOTE)
    _apply(mount, body)
    return _disks(mount.machine)


@router.delete("/{int:machine_id}/mounts/{int:mount_id}", response=Disks)
def drop_mount(request, machine_id: int, mount_id: int):
    mount = get_object_or_404(MachineMount.objects.select_related("machine"), pk=mount_id, machine_id=machine_id)
    if _is_overlay(mount.machine, mount):
        raise ValidationError(OVERLAY_NOTE)
    mount.delete()
    return _disks(get_object_or_404(Machine, pk=machine_id))


@router.put("/{int:machine_id}/overlay", response=Disks)
def set_overlay(request, machine_id: int, body: OverlayIn):
    """Выбрать диск отличий машины (или снять выбор). Диск ложится над всеми дисками машины; прежний остаётся в мире отдельным."""
    machine = get_object_or_404(Machine, pk=machine_id)
    if body.volume is None:
        if machine.overlay_id:
            machine.mounts.filter(volume_id=machine.overlay_id, mount_path="/", volume_path="").delete()
            machine.overlay = None
            machine.save(update_fields=["overlay"])
        return _disks(machine)
    volume = get_object_or_404(Volume, pk=body.volume)
    if volume.pk not in {v.pk for v in _overlay_choices(machine)} and volume.pk != machine.overlay_id:
        raise ValidationError("Этот диск нельзя сделать отличиями: он смонтирован в другом месте, это образ ОС или отличия другой машины.")
    assign_overlay(machine, volume)
    return _disks(machine)


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


