"""Корень машины: том, смонтированный на «/», в который ложатся файлы игрока и автора, пока у машины нет ничего другого."""
from filesystem.models import Volume
from machines.models import MachineMount


def ensure_root(machine):
    """Том на корне машины (создаётся при первой записи, если машина ещё ничего не монтировала на «/»). Возвращает том."""
    mount = MachineMount.objects.filter(machine=machine, mount_path="/").select_related("volume").order_by("-order").first()
    if mount is not None:
        return mount.volume
    base = f"{machine.label}-root"
    slug, number = base, 1
    while Volume.objects.filter(slug=slug).exists():
        number += 1
        slug = f"{base}-{number}"
    volume = Volume.objects.create(slug=slug, label=f"Корень {machine.label}")
    MachineMount.objects.create(machine=machine, volume=volume, mount_path="/", order=0)
    return volume
