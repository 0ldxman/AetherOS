"""Сырые байты файла так, как их видит игрок (blk, txtx, cvt, вьювер raw).

У файла нет хранимых данных, но у него есть то, на что он указывает: ассет, запись вики, приложение. Из этого строятся
байты: настоящие данные там, где они есть, шум там, где их нет. Слои файла меняют вид байтов (шифр прячет, base64
кодирует, повреждение портит блоки). Размер файла это длина этих байтов.
"""
from filesystem.rawview.generate import RawFile, build_raw

__all__ = ["RawFile", "build_raw", "build_raw_cached"]


def build_raw_cached(machine_file, session_state="", keys=frozenset(), seconds=120):
    """build_raw с кэшем на короткое время: вьювер читает файл десятками запросов с диапазонами, а ассет лежит в Nextcloud."""
    from django.core.cache import cache

    from filesystem.rawview.source import resolve_payload

    payload = resolve_payload(machine_file, keys)
    key = (
        f"rawbytes:{machine_file.pk}:{machine_file.updated_at.timestamp()}:{hash(session_state)}:{payload.stamp}:"
        f"{payload.locked}"
    )
    data = cache.get(key)
    if data is None:
        data = build_raw(machine_file, session_state, keys).data
        if len(data) <= 4 * 1024 * 1024:
            cache.set(key, data, seconds)
    return data
