"""Файлы в хранилище (Nextcloud) как содержимое объектов: определение вида и поиск по ссылке.

Используется и вьюхами (assets/views.py), и виджетами документов (documents/widgets), поэтому вид файла определяется в одном месте.
Файл это содержимое объекта (Item.file_id): отдельной таблицы ассетов нет.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import PurePosixPath

TEXT_EXTENSIONS = frozenset({".txt", ".log", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".sh", ".py", ".sql"})
TEXT_CONTENT_TYPES = frozenset({"application/json", "application/xml"})

AUDIO, VIDEO, IMAGE, PDF, TEXT, RAW = "AUDIO", "VIDEO", "IMAGE", "PDF", "TEXT", "RAW"

# Виды, для которых в вики есть собственный виджет. Всё остальное рисуется как «скачать файл».
WIDGET_KIND_BY_VIEWER = {AUDIO: "audio", VIDEO: "video", IMAGE: "image"}
FILE_KIND = "file"

# asset:<слаг или UUID> (слаг объекта). Группы через ":" пока не поддерживаются.
_REF = re.compile(r"(?:asset:)?([a-z0-9][a-z0-9_-]{0,63})")


@dataclass
class AssetRef:
    """Файл объекта так, как его видят виджеты вики: имя, слаг, публичный адрес, имя файла, тип и размер."""

    item: object
    name: str
    slug: str
    public_id: uuid.UUID
    filename: str
    content_type: str
    size: int | None


def asset_ref(item) -> AssetRef:
    return AssetRef(item=item, name=item.name, slug=item.slug, public_id=item.public_id, filename=item.file_name, content_type=item.file_type, size=item.file_size)


def guess_content_type(filename: str) -> str:
    return guess_type(filename)[0] or "application/octet-stream"


def resolve_viewer_type(filename: str, content_type: str) -> str:
    """Вид просмотра по типу и имени файла."""
    extension = PurePosixPath(filename).suffix.lower()
    if content_type.startswith("audio/"):
        return AUDIO
    if content_type.startswith("video/"):
        return VIDEO
    if content_type.startswith("image/"):
        return IMAGE
    if content_type == "application/pdf" or extension == ".pdf":
        return PDF
    if content_type.startswith("text/") or extension in TEXT_EXTENSIONS or content_type in TEXT_CONTENT_TYPES:
        return TEXT
    return RAW


def asset_viewer_type(asset) -> str:
    """Вид по закэшированным сведениям о файле, без похода в Nextcloud. Пока сведений нет, это RAW («скачать»)."""
    if hasattr(asset, "file_name"):
        return resolve_viewer_type(asset.file_name, asset.file_type)
    return resolve_viewer_type(asset.filename, asset.content_type)


def asset_widget_kind(asset) -> str:
    """'audio' | 'video' | 'image' | 'file': какой виджет рисовать."""
    return WIDGET_KIND_BY_VIEWER.get(asset_viewer_type(asset), FILE_KIND)


def find_asset(ref: str) -> AssetRef | None:
    """Объект с файлом по ссылке из разметки: 'asset:theme-01', 'theme-01' (слаг объекта) или UUID. Один-два запроса в БД."""
    from filesystem.models import Item

    match = _REF.fullmatch((ref or "").strip().lower())
    if not match:
        return None
    key = match.group(1)
    found = Item.objects.exclude(file_id="").filter(slug=key).first()
    if found is None:
        try:
            public_id = uuid.UUID(key)
        except ValueError:
            return None
        found = Item.objects.exclude(file_id="").filter(public_id=public_id).first()
    return asset_ref(found) if found is not None else None


def read_asset_bytes(asset, limit):
    """Байты файла из Nextcloud (не больше limit; больше нельзя: вернётся None). Нужны для сырого вида файла."""
    from assets.nextcloud import NextcloudClient

    client = NextcloudClient.from_settings()
    file = client.get_file_by_id(asset.file_id)
    if file is None or file.is_directory:
        return None
    if file.size is not None and file.size > limit:
        return None

    response = client.stream(file.path)
    try:
        data = b"".join(response.iter_content(65536))
    finally:
        response.close()
    return data if len(data) <= limit else None


ROOT_FOLDER = "AETHER"


def list_folder(path=ROOT_FOLDER):
    """Содержимое папки Nextcloud внутри AETHER для выбора файла: {"path": "/AETHER/...", "items": [...]}.
    ValueError: путь вне AETHER. RuntimeError: Nextcloud не ответил."""
    import logging

    from assets.nextcloud import NextcloudClient

    path = (path or ROOT_FOLDER).strip("/")
    if not path or (path != ROOT_FOLDER and not path.startswith(ROOT_FOLDER + "/")):
        raise ValueError("Invalid path.")
    try:
        found = NextcloudClient.from_settings().list(path)
    except Exception as exc:
        logging.getLogger(__name__).exception("Nextcloud browse failed: %s", path)
        raise RuntimeError("Nextcloud request failed.") from exc

    result = []
    if path != ROOT_FOLDER:
        result.append({"file_id": None, "name": "..", "path": "/" + path.rsplit("/", 1)[0], "is_directory": True, "is_parent": True})
    for entry in found:
        result.append({"file_id": entry.file_id, "name": entry.filename, "path": entry.path, "is_directory": entry.is_directory, "is_parent": False})
    result.sort(key=lambda row: (not row["is_directory"], not row["is_parent"], row["name"].lower()))
    return {"path": "/" + path, "items": result}
