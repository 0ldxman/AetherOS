"""Размер файла, который видит игрок (ls -l, cnt).

Это длина сырых байтов файла (filesystem/rawview): у ассета настоящий размер, у записи вики размер её контейнера, у
файла без источника указанный автором (MachineFile.size) или выдуманный по пути, всегда один и тот же. Слои меняют
размер, как в жизни (base64 длиннее, шифр той же длины). Папка, как в Unix, 4096.
"""
from django.core.cache import cache

from filesystem.rawview import build_raw
from filesystem.rawview.source import resolve_payload

DIRECTORY_SIZE = 4096
CACHE_SECONDS = 300


def keys_in_file(machine_file):
    from filesystem.rawview.keys import slugs_of

    return slugs_of(machine_file)


def file_size(machine_file, session_state="", keys=frozenset(), viewer=None):
    """Размер файла в байтах."""
    if machine_file.file_type == "DIRECTORY":
        return DIRECTORY_SIZE

    held = keys_in_file(machine_file)                                  # блоки ключей меняют длину байтов
    layered = bool((machine_file.state or "").strip() or (session_state or "").strip()) or bool(held)
    if machine_file.size is not None and not layered:
        return machine_file.size

    payload = resolve_payload(machine_file, keys, viewer=viewer)
    if payload.kind == "asset" and payload.size is not None and not layered:
        return payload.size                        # ассет без слоёв: настоящий размер, без похода в Nextcloud

    key = f"rawsize:{machine_file.pk}:{machine_file.updated_at.timestamp()}:{hash(session_state)}:{payload.stamp}:{','.join(held)}"
    size = cache.get(key)
    if size is None:
        size = build_raw(machine_file, session_state, keys, viewer=viewer).size
        cache.set(key, size, CACHE_SECONDS)
    return size


def human_size(size):
    """512, 12K, 1.4M: как ls -h."""
    value = float(size)
    for unit in ("", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{int(value)}{unit}" if value >= 10 or not unit else f"{value:.1f}{unit}"
        value /= 1024
