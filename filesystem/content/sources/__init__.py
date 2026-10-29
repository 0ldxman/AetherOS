"""Виды содержимого файлов машины.

Что лежит в файле, определяют его объект (текст, ассет, ссылка, сцена карты, письмо, ключ) или собственное содержимое игрока
(подпись, вырезка); папка-архив отдельный вид. Каждый вид описан одним классом (filesystem/content/sources/items.py), реестр ниже выбирает
первый подходящий. Байты (rawview) и окно cnt (content) спрашивают реестр и сами содержимое не разбирают.

Новый вид содержимого это новый класс и строка в SOURCES.
"""
from filesystem.content.sources.base import READ_LIMIT, Content, Payload, page_window, site_url, text_window
from filesystem.content.sources.items import (
    ArchiveSource, AssetSource, BlankSource, KeySource, LinkSource, MessageSource, OwnSource, SceneSource, TextSource,
)
from filesystem.content.sources.log import LogSource

# порядок важен: пустой файл приходит последним, потому что принимает всё
SOURCES = (
    ArchiveSource(), OwnSource(), AssetSource(), LinkSource(), SceneSource(), MessageSource(), KeySource(), LogSource(), TextSource(), BlankSource(),
)

__all__ = ["READ_LIMIT", "SOURCES", "Content", "Payload", "page_window", "payload_for", "site_url", "source_for", "text_window", "window_for"]


def source_for(entry):
    """Класс вида содержимого этого файла вида машины."""
    return next(source for source in SOURCES if source.accepts(entry))


def payload_for(entry, view=None, keys=frozenset(), reader=None, viewer=None):
    """Источник данных файла."""
    return source_for(entry).payload(entry, view, keys, reader, viewer)


def window_for(entry):
    """Окно, которое открывает cnt для файла, если слои его не закрывают."""
    return source_for(entry).window(entry)
