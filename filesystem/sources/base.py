"""Что умеет любой вид содержимого файла: дать байты и сказать, какое окно открыть.

Вид содержимого узнаётся по адресу (MachineFile.url). Всё, что про него известно, лежит в одном классе: как разобрать адрес,
какие байты получить, как их собирать (layout) и что показывает cnt. Реестр (filesystem.sources) выбирает класс по адресу.
"""
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from django.urls import get_script_prefix

READ_LIMIT = 8 * 1024 * 1024


@dataclass
class Payload:
    kind: str = "none"                         # none | wiki | asset | map | mail | app | key | slice | archive | signature
    body: bytes = b""                          # текст (wiki, map) или готовые байты (asset, app)
    fmt: str | None = None                     # формат, который диктует источник (тип записи вики)
    meta: dict = field(default_factory=dict)
    views: dict = field(default_factory=dict)  # тело в видах формата (flatten.STYLES): текст, html, объекты, ocr
    locked: bool = False                       # доступа нет: тело подменяется шумом
    stamp: str = ""                            # что меняется вместе с источником (для кэша размера)
    size: int | None = None                    # размер источника, если он известен без чтения (ассет)
    build: object = None                       # как получить тело лениво (архив: читать всех членов ради размера незачем)
    layout: str = "noise"                      # как собирать байты: noise | format | asset | raw | app | archive (generate._content)
    real: bool = False                         # в байтах настоящие данные, а не шум: в них вкладываются блоки ключей
    default_fmt: str | None = None             # формат, если ни слой, ни источник его не назвали (layout format)


@dataclass
class Content:
    url: str = ""
    error: str = ""     # "locked" | "empty" | "bad_path"


@dataclass(frozen=True)
class Address:
    """Адрес содержимого, разобранный один раз: чистая строка, части пути и запрос."""

    url: str
    parts: list
    query: dict

    @classmethod
    def parse(cls, raw):
        url = (raw or "").strip().lstrip("/")
        parsed = urlsplit(url)
        return cls(url, [part for part in parsed.path.split("/") if part], parse_qs(parsed.query))


def page_window(url):
    """Окно приложения сайта по внутреннему адресу. Чужие и абсолютные адреса не открываются."""
    url = url.strip()
    if "://" in url or url.startswith("//") or "\\" in url or url.startswith("/"):
        return Content(error="bad_path")

    return Content(url=get_script_prefix().rstrip("/") + "/" + url)


class Source:
    """Вид содержимого. Новый вид это новый класс, записанный в реестр (filesystem/sources/__init__.py)."""

    name = ""

    def accepts(self, address):
        """Мой ли это адрес (для байтов)."""
        return False

    def payload(self, machine_file, address, keys, reader, viewer):
        raise NotImplementedError

    def shows(self, url):
        """Мой ли это адрес для окна cnt, если он особый. Обычный адрес открывается как страница сайта (page_window)."""
        return False

    def window(self, url, path):
        return page_window(url)
