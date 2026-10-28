"""Экземпляр тома для монтирования: где живёт состояние игрока.

Локальное монтирование на машине M даёт экземпляр (том, M). Сетевое подключение своего экземпляра не имеет: игрок работает с видом
хоста, то есть с экземплярами самого хоста (filesystem/machine_view.py, machines/connection.py).
"""
from filesystem.models import VolumeInstance


def get_or_create(volume_id, host_id):
    instance, _ = VolumeInstance.objects.get_or_create(volume_id=volume_id, host_id=host_id)
    return instance
