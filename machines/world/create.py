"""Новая машина: с нуля (корень пустой, по шаблону файловой структуры или существующий том) или по образцу другой машины.

По образцу копируется то, из чего машина состоит: учётки (кроме рабочих учёток игроков), свои группы и пути, экспорты, политика,
монтирования. Том, который смонтирован только на образце (его личный корень и отличия), копируется: у новой машины он свой.
Том, общий с другими машинами (образ системы, архив), остаётся общим.
"""
from django.db import transaction

from filesystem.manager.filemanager import apply_template, copy_volume
from filesystem.models import Volume, VolumeTemplate
from machines.models import Export, Group, Machine, MachineMount, MachineProfile, Place

PROFILE_FIELDS = ("name", "freq", "login", "password_hash", "key_condition", "ttl", "cooldown", "groups", "root", "entry_policy", "kick_message")


def _slug(base):
    slug, number = base, 1
    while Volume.objects.filter(slug=slug).exists():
        number += 1
        slug = f"{base}-{number}"
    return slug


@transaction.atomic
def create_volume(slug, name="", label="", uuid=None, template=None, machine=None, mount_path=""):
    """Новый том: пустой или по шаблону файловой структуры (template: pk VolumeTemplate), по желанию сразу смонтированный на машину."""
    disk = Volume(slug=slug.strip(), name=name.strip(), label=label.strip())
    if uuid:
        disk.uuid = uuid
    disk.full_clean()
    disk.save()
    apply_template(disk, VolumeTemplate.objects.get(pk=template) if template else None)
    if machine:
        MachineMount(machine=Machine.objects.get(pk=machine), volume=disk, mount_path=mount_path).full_clean()
        MachineMount.objects.create(machine_id=machine, volume=disk, mount_path=mount_path)
    return disk


@transaction.atomic
def create_machine(hostname, name, system, status=Machine.Status.OFFLINE, root="empty", template=None, volume=None):
    """root: empty (корень появится при первой записи), template (новый том по шаблону VolumeTemplate) или volume (готовый том)."""
    machine = Machine(hostname=hostname or None, name=name or hostname, system=system, status=status)
    machine.full_clean()
    machine.save()
    if root == "template":
        found = VolumeTemplate.objects.get(pk=template)
        disk = Volume.objects.create(slug=_slug(f"{machine.label}-root"), label=f"Корень {machine.label}")
        apply_template(disk, found)
        MachineMount.objects.create(machine=machine, volume=disk, mount_path="/")
    elif root == "volume":
        MachineMount.objects.create(machine=machine, volume=Volume.objects.get(pk=volume), mount_path="/")
    return machine


@transaction.atomic
def clone_machine(source, hostname, name="", status=None):
    machine = Machine(
        hostname=hostname or None, name=name or hostname, system=source.system, status=status or source.status, entry_policy=source.entry_policy,
    )
    machine.full_clean()
    machine.save()
    old_host = source.label
    for profile in source.profiles.filter(user__isnull=True):
        copy = MachineProfile(machine=machine, **{field: getattr(profile, field) for field in PROFILE_FIELDS})
        copy.mail = profile.mail.replace(f"@{old_host}", f"@{machine.label}") if profile.mail else ""
        copy.save()
    for group in Group.objects.filter(machine=source):
        Group.objects.create(machine=machine, name=group.name, privileges=group.privileges, everyone=group.everyone, disabled=group.disabled)
    for place in Place.objects.filter(machine=source):
        Place.objects.create(machine=machine, name=place.name, path=place.path)
    for export in source.exports.all():
        Export.objects.create(machine=machine, path=export.path)
    for mount in source.mounts.select_related("volume"):
        disk = mount.volume
        if disk is not None and not disk.mounts.exclude(machine=source).exists():
            disk = copy_volume(disk, _slug(disk.slug.replace(old_host, machine.label) if old_host in disk.slug else f"{disk.slug}-{machine.label}"),
                               name=disk.name, label=(disk.label or disk.slug).replace(old_host, machine.label))
        MachineMount.objects.create(
            machine=machine, volume=disk, host=mount.host, host_path=mount.host_path, account=mount.account,
            volume_path=mount.volume_path, mount_path=mount.mount_path, mode=mount.mode, order=mount.order,
        )
    return machine
