"""Виды содержимого файлов машины.

MachineFile.url указывает, что лежит в файле: ключ, подпись, вырезка, ассет, запись вики, карта, письмо, приложение. Архив
адреса не имеет: это файл с файлами под его путём. Каждый вид описан одним классом (filesystem/sources/*.py), реестр ниже
выбирает класс по адресу. Байты (rawview) и окно cnt (content) спрашивают реестр и не разбирают адреса сами.

Новый вид содержимого это новый класс и строка в SOURCES.
"""
from filesystem.sources import archive
from filesystem.sources.apps import AppSource, AssetSource, MailSource, MapSource, WikiSource
from filesystem.sources.base import READ_LIMIT, Address, Content, Payload, page_window
from filesystem.sources.keys import KeySource, SignatureSource
from filesystem.sources.slices import SliceSource

# порядок важен: приложение приходит последним, потому что принимает всё под apps/
SOURCES = (KeySource(), SignatureSource(), SliceSource(), AssetSource(), WikiSource(), MapSource(), MailSource(), AppSource())

__all__ = ["READ_LIMIT", "SOURCES", "Address", "Content", "Payload", "resolve_payload", "resolve_window", "source_for"]


def source_for(address):
    """Класс вида содержимого по разобранному адресу или None, если адрес ни на что не указывает."""
    return next((source for source in SOURCES if source.accepts(address)), None)


def resolve_payload(machine_file, keys, reader=None, viewer=None):
    """Источник данных файла по его адресу содержимого."""
    address = Address.parse(machine_file.url)
    if not address.url:
        if archive.claims(machine_file):
            return archive.payload(machine_file, keys, reader, viewer)
        return Payload()

    source = source_for(address)
    return source.payload(machine_file, address, keys, reader, viewer) if source else Payload()


def resolve_window(url, path):
    """Окно, которое открывает cnt по адресу url у файла по пути path."""
    url = (url or "").strip()
    if not url:
        return Content(error="empty")

    source = next((source for source in SOURCES if source.shows(url)), None)
    return source.window(url, path) if source else page_window(url)
