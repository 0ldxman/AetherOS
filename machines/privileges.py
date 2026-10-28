"""Привилегии записи: что она может делать на машине помимо прав на файлы.

Привилегии входят в группы (machines.models.Group), у записи привилегии складываются по всем её группам, у root есть все.
Список закрытый: движок знает эти имена, а какая группа какие из них даёт, решает автор.
"""
from dataclasses import dataclass

PRIVILEGES = {
    "clock": "Менять время машины",
    "backup": "Читать любые файлы мимо прав",
    "restore": "Писать в любые файлы мимо прав",
    "chown": "Менять владельца файлов",
    "mount": "Подключать диски",
    "bridge": "Открывать мосты на другие машины (rshell, туннель)",
    "transfer": "Передавать файлы между машинами (xfer, nget)",
}

# группы, которые есть, пока ни у типа системы, ни у машины своих нет: игрок ходит по мостам и передаёт файлы, как и раньше
DEFAULT_GROUPS = {"users": {"privileges": ["bridge", "transfer"], "everyone": True}}


@dataclass(frozen=True)
class Principal:
    """Кто действует: запись машины, её группы и привилегии."""

    login: str
    groups: frozenset = frozenset()
    privileges: frozenset = frozenset()
    root: bool = False

    def has(self, code):
        return self.root or code in self.privileges
