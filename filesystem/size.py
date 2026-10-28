"""Размер файла, который видит игрок (ls -l, cnt).

Это длина сырых байтов файла (filesystem/rawview): у ассета настоящий размер, у текста размер его контейнера, у файла без
содержимого указанный автором (Item.size) или выдуманный по слагу, всегда один и тот же. Слои меняют размер, как в жизни
(base64 длиннее, шифр той же длины). Папка, как в Unix, 4096.
"""
from django.core.cache import cache

from filesystem.rawview import build_raw
from filesystem.sources import payload_for

DIRECTORY_SIZE = 4096
CACHE_SECONDS = 300


def keys_in_file(item):
    from filesystem.rawview.keys import slugs_of

    if item is None:
        return []
    signed = [f"{row.key.slug}:{row.valid}:{row.date}" for row in item.signatures.select_related("key")]
    return [*slugs_of(item), *signed]


def file_size(entry, view=None, keys=frozenset(), viewer=None):
    """Размер файла в байтах."""
    if entry.is_dir:
        return DIRECTORY_SIZE

    held = keys_in_file(entry.item)                                    # блоки ключей меняют длину байтов
    layered = bool((entry.state or "").strip() or (entry.progress or "").strip()) or bool(held)
    item = entry.item
    declared = item is not None and item.size is not None and not item.body.strip() and not (item.asset_id or item.scene_id or item.message_id) \
        and entry.player is None
    if declared and not layered:
        return item.size

    payload = payload_for(entry, view, keys, viewer=viewer)
    if payload.size is not None and not layered:
        return payload.size                        # ассет без слоёв: настоящий размер, без похода в Nextcloud

    key = f"rawsize:{entry.path}:{item.pk if item is not None else 0}:{hash((entry.state, entry.progress))}:{payload.stamp}:{','.join(held)}"
    size = cache.get(key)
    if size is None:
        size = build_raw(entry, view, keys, viewer=viewer).size
        cache.set(key, size, CACHE_SECONDS)
    return size


def human_size(size):
    """512, 12K, 1.4M: как ls -h."""
    value = float(size)
    for unit in ("", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{int(value)}{unit}" if value >= 10 or not unit else f"{value:.1f}{unit}"
        value /= 1024
