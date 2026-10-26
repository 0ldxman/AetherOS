"""Реестр форматов и кодировок: читается из базы (админка), на короткое время запоминается.

Здесь нет ни одного формата в коде: scan, doc, pdf, utf16 и остальные это записи FileFormat и FileEncoding. Код знает
только виды устройства (signature, text, chunks, package) и виды кодировок (codec, hex, rot, ...).
"""
from dataclasses import dataclass, field

from django.core.cache import cache

KEY = "rawview:registry:1"
SECONDS = 60


@dataclass(frozen=True)
class PartDef:
    name: str
    source: str
    value: str = ""


@dataclass(frozen=True)
class FormatDef:
    name: str
    title: str
    extension: str
    kind: str
    magic: bytes
    template: str
    parts: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class EncodingDef:
    name: str
    kind: str
    param: str = ""


def _load():
    from filesystem.models import FileEncoding, FileFormat

    formats = {}
    for item in FileFormat.objects.prefetch_related("parts"):
        magic = bytes.fromhex(item.magic) if item.magic.strip() else b""
        parts = tuple(PartDef(p.name, p.source, p.value) for p in item.parts.all())
        formats[item.name] = FormatDef(item.name, item.title or item.name, item.extension, item.kind, magic, item.template, parts)
    encodings = {item.name: EncodingDef(item.name, item.kind, item.param) for item in FileEncoding.objects.all()}
    return formats, encodings


def _registry():
    loaded = cache.get(KEY)
    if loaded is None:
        loaded = _load()
        cache.set(KEY, loaded, SECONDS)
    return loaded


def invalidate(**kwargs):
    cache.delete(KEY)


def format_named(name):
    return _registry()[0].get((name or "").strip().lower())


def all_formats():
    return list(_registry()[0].values())


def encoding_named(name):
    return _registry()[1].get((name or "").strip().lower())


def format_for_extension(extension):
    """Формат с таким расширением имени файла (.scan -> scan); так тип записи вики находит свой формат."""
    wanted = (extension or "").strip().lower()
    return next((item for item in _registry()[0].values() if item.extension and item.extension == wanted), None)

