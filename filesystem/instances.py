"""Экземпляр тома для монтирования: где живёт состояние игрока.

local на машине M даёт экземпляр (том, M). remote указывает на экземпляр хоста: хост это единственная машина, у которой этот
том смонтирован local; если такой машины нет (или их несколько), экземпляр общий без машины. Правило хоста предварительное,
оно уточняется в фазе удалённых монтирований.
"""
from filesystem.models import VolumeInstance


def host_id_of(mount, local_hosts):
    """Машина-хозяин экземпляра для монтирования; local_hosts это {id тома: {id машин с local-монтированием}}."""
    if mount.mode == "local":
        return mount.machine_id
    owners = local_hosts.get(mount.volume_id, set()) - {mount.machine_id}
    return next(iter(owners)) if len(owners) == 1 else None


def get_or_create(volume_id, host_id):
    instance, _ = VolumeInstance.objects.get_or_create(volume_id=volume_id, host_id=host_id)
    return instance
