"""Размер файла, который видит игрок (ls -l, cnt).

Данных у файла нет, есть только описание, поэтому размер берётся так: если автор указал его в админке (MachineFile.size),
это он; иначе размер выдумывается один раз и навсегда из машины и пути файла, так что везде (ls, cnt, копии, перенос
между машинами) число одно и то же. Папка, как в Unix, 4096.
"""
import hashlib

DIRECTORY_SIZE = 4096
GENERATED_MIN, GENERATED_MAX = 180, 48_000


def file_size(machine_file):
    """Размер файла в байтах."""
    if machine_file.file_type == "DIRECTORY":
        return DIRECTORY_SIZE
    if machine_file.size is not None:
        return machine_file.size

    digest = hashlib.sha256(f"{machine_file.machine.hostname}:{machine_file.path}".encode()).digest()
    return GENERATED_MIN + int.from_bytes(digest[:4], "big") % (GENERATED_MAX - GENERATED_MIN + 1)


def human_size(size):
    """512, 12K, 1.4M: как ls -h."""
    value = float(size)
    for unit in ("", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{int(value)}{unit}" if value >= 10 or not unit else f"{value:.1f}{unit}"
        value /= 1024
