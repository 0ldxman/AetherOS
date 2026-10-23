"""Общая логика ассетов: определение типа и поиск по ссылке.

Используется и вьюхами (assets/views.py), и вики-виджетами (wiki/widgets.py),
поэтому тип файла определяется в одном месте.
"""

from __future__ import annotations

import re
import uuid
from mimetypes import guess_type
from pathlib import PurePosixPath

from .models import Asset

TEXT_EXTENSIONS = frozenset(
    {
        ".txt", ".log", ".md", ".csv", ".json", ".xml",
        ".yaml", ".yml", ".ini", ".cfg", ".conf",
        ".sh", ".py", ".sql",
    }
)

TEXT_CONTENT_TYPES = frozenset(
    {"application/json", "application/xml"}
)

# Виды, для которых в вики есть собственный виджет.
# Всё остальное рисуется как «скачать файл».
WIDGET_KIND_BY_VIEWER = {
    Asset.ViewerType.AUDIO: "audio",
    Asset.ViewerType.VIDEO: "video",
    Asset.ViewerType.IMAGE: "image",
}
FILE_KIND = "file"

# asset:<slug или UUID>. Группы через ":" пока не поддерживаются.
_REF = re.compile(r"(?:asset:)?([a-z0-9][a-z0-9_-]{0,63})")


def guess_content_type(filename: str) -> str:
    return guess_type(filename)[0] or "application/octet-stream"


def resolve_viewer_type(
    asset: Asset,
    filename: str,
    content_type: str,
) -> str:
    """AUTO -> подходящий viewer по типу файла.

    Явно заданный у ассета viewer_type имеет приоритет.
    """
    if asset.viewer_type != Asset.ViewerType.AUTO:
        return asset.viewer_type

    extension = PurePosixPath(filename).suffix.lower()

    if content_type.startswith("audio/"):
        return Asset.ViewerType.AUDIO

    if content_type.startswith("video/"):
        return Asset.ViewerType.VIDEO

    if content_type.startswith("image/"):
        return Asset.ViewerType.IMAGE

    if content_type == "application/pdf" or extension == ".pdf":
        return Asset.ViewerType.PDF

    if (
        content_type.startswith("text/")
        or extension in TEXT_EXTENSIONS
        or content_type in TEXT_CONTENT_TYPES
    ):
        return Asset.ViewerType.TEXT

    return Asset.ViewerType.RAW


def asset_viewer_type(asset: Asset) -> str:
    """Тип ассета по закэшированным метаданным, без похода в Nextcloud.

    Если метаданные ещё не заполнены (filename пуст), AUTO даёт RAW,
    то есть «скачать». Явный viewer_type работает и без метаданных.
    """
    return resolve_viewer_type(
        asset,
        asset.filename,
        asset.content_type,
    )


def asset_widget_kind(asset: Asset) -> str:
    """'audio' | 'video' | 'image' | 'file': какой виджет рисовать."""
    return WIDGET_KIND_BY_VIEWER.get(
        asset_viewer_type(asset),
        FILE_KIND,
    )


def find_asset(ref: str) -> Asset | None:
    """Ассет по ссылке из разметки: 'asset:theme-01', 'theme-01' или UUID.

    Один запрос в БД. Мусор и несуществующие ссылки дают None.
    """
    match = _REF.fullmatch((ref or "").strip().lower())
    if not match:
        return None

    key = match.group(1)

    # Сначала slug (он не может быть валидным UUID с дефисами в 8-4-4-4-12,
    # но на всякий случай slug проверяем первым).
    asset = Asset.objects.filter(slug=key).first()
    if asset is not None:
        return asset

    try:
        public_id = uuid.UUID(key)
    except ValueError:
        return None

    return Asset.objects.filter(public_id=public_id).first()