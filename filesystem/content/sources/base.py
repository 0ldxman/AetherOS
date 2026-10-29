"""Что умеет любой вид содержимого файла: дать байты и сказать, какое окно открыть.

Вид содержимого определяется по самому файлу вида машины (filesystem.machine_view.Entry): что лежит в его объекте (ассет, ссылка,
сцена карты, письмо, текст) или собственное содержимое игрока (подпись, вырезка). Всё, что про вид известно, лежит в одном классе:
когда он подходит (accepts), какие байты (payload), как их собирать (layout) и какое окно открывает cnt (window).
"""
from dataclasses import dataclass, field

from django.urls import get_script_prefix, reverse
from django.utils.http import urlencode

READ_LIMIT = 8 * 1024 * 1024


@dataclass
class Payload:
    kind: str = "none"                         # none | text | asset | map | mail | link | key | own | archive
    body: bytes = b""                          # текст или готовые байты
    fmt: str | None = None                     # формат, который диктует источник (формат объекта)
    meta: dict = field(default_factory=dict)
    views: dict = field(default_factory=dict)  # тело в видах формата (flatten.STYLES): текст, html, объекты, ocr
    locked: bool = False                       # доступа нет: тело подменяется шумом
    stamp: str = ""                            # что меняется вместе с источником (для кэша размера)
    size: int | None = None                    # размер источника, если он известен без чтения (ассет)
    build: object = None                       # как получить тело лениво (архив: читать всех членов ради размера незачем)
    layout: str = "noise"                      # как собирать байты: noise | format | asset | raw | archive (generate._content)
    real: bool = False                         # в байтах настоящие данные, а не шум: в них вкладываются блоки ключей
    default_fmt: str | None = None             # формат, если ни слой, ни источник его не назвали (layout format)


@dataclass
class Content:
    url: str = ""
    error: str = ""     # "locked" | "empty" | "bad_path"


def site_url(path):
    """Адрес страницы сайта с учётом префикса: apps/map/?scene=x -> /prefix/apps/map/?scene=x."""
    return get_script_prefix().rstrip("/") + "/" + path.lstrip("/")


def text_window(path):
    """Файл показывается текстом: то же, что в raw, но в простом окне."""
    return Content(url=reverse("fsview:text") + "?" + urlencode({"path": path}))


def page_window(url):
    """Окно приложения сайта по внутреннему адресу (ответ слоя на cnt). Чужие и абсолютные адреса не открываются."""
    url = url.strip()
    if not url:
        return Content(error="empty")
    if "://" in url or url.startswith("//") or "\\" in url or url.startswith("/"):
        return Content(error="bad_path")
    return Content(url=site_url(url))


class Source:
    """Вид содержимого. Новый вид это новый класс, записанный в реестр (filesystem/content/sources/__init__.py)."""

    name = ""

    def accepts(self, entry):
        return False

    def payload(self, entry, view, keys, reader, viewer):
        raise NotImplementedError

    def window(self, entry):
        return Content(error="empty")
