"""Сырые байты файла так, как их видит игрок (blk, txtx, cvt, вьювер raw).

У файла нет хранимых данных, но у него есть то, на что он указывает: ассет, запись вики, приложение. Из этого строятся
байты: настоящие данные там, где они есть, шум там, где их нет. Слои файла меняют вид байтов (шифр прячет, base64
кодирует, повреждение портит блоки). Размер файла это длина этих байтов.
"""
from filesystem.rawview.generate import RawFile, build_raw

__all__ = ["RawFile", "build_raw", "build_raw_cached", "detect"]


def build_raw_cached(machine_file, session_state="", keys=frozenset(), seconds=120, viewer=None):
    """build_raw с кэшем на короткое время: вьювер читает файл десятками запросов с диапазонами, а ассет лежит в Nextcloud."""
    from django.core.cache import cache

    from filesystem.rawview import keys
    from filesystem.sources import resolve_payload

    payload = resolve_payload(machine_file, keys, viewer=viewer)
    key = (
        f"rawbytes:{machine_file.pk}:{machine_file.updated_at.timestamp()}:{hash(session_state)}:{payload.stamp}:"
        f"{payload.locked}:{','.join(keys.slugs_of(machine_file))}:{signed_stamp(machine_file)}"
    )
    data = cache.get(key)
    if data is None:
        data = build_raw(machine_file, session_state, keys, viewer=viewer).data
        if len(data) <= 4 * 1024 * 1024:
            cache.set(key, data, seconds)
    return data


def signed_stamp(machine_file):
    return ",".join(f"{row.key.slug}:{row.valid}:{row.date}" for row in machine_file.signatures.select_related("key"))


def viewer_formats():
    """Форматы реестра для вьювера raw (JSON): байтовые сигнатуры и текстовые начала. Вьювер добавляет их к своей таблице."""
    import json

    from filesystem.rawview import formats, registry

    found = []
    for item in registry.all_formats():
        entry = {"name": item.title or item.name}
        if item.kind == "text":
            start = formats.prefix(item.name)
            if not start:
                continue
            entry["prefix"] = start
        elif item.magic:
            entry["bytes"] = list(item.magic)
        else:
            continue
        found.append(entry)
    return json.dumps(found)



def detect(data):
    """Формат реестра, с чьей сигнатуры (или текстового начала) начинаются байты, или None. Самое длинное совпадение побеждает."""
    from filesystem.rawview import formats, registry

    best, length = None, 0
    for item in registry.all_formats():
        start = formats.prefix(item.name).encode() if item.kind == "text" else item.magic
        if start and data.startswith(start) and len(start) > length:
            best, length = item, len(start)
    return best
