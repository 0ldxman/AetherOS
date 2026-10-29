"""Общее для виджетов: реестр, разбор аргументов, ассеты."""
import re

from django.urls import NoReverseMatch, reverse

from assets.services import find_asset
from collections import namedtuple


TONES = ("red", "green", "blue", "grey")


ALIGNS = ("left", "center", "right")


MAX_LINES = 200           # сколько строк берём у log и checks


BARCODE_MAX_LEN = 40      # длина значения штрихкода


MENU_MAX_ITEMS = 12       # пунктов меню в шапке сайта


IMAGE_RATIOS = {"16:9": "16-9", "4:3": "4-3", "3:2": "3-2", "1:1": "1-1", "3:4": "3-4", "9:16": "9-16"}


ASSET_CONTENT_URL = "asset_viewer:content"


ASSET_VIEWER_URL = "asset_viewer:viewer"


DIVIDER_STYLES = ("line", "double", "dashed", "dotted", "thick", "stars")


# Code 39: шрифт Libre Barcode 39 рисует штрихи по символам *ТЕКСТ*
_BARCODE_ALLOWED = re.compile(r"[^A-Z0-9 .$/+%-]")


# fn: функция виджета
# raw: True, если тело блока читается как есть (строки), а не как параметры
# positional: какой параметр получает слово без «ключ=» в строке открытия
# line: True - виджет всегда в одну строку, даже без параметров (закрывающая "::" не нужна)
Widget = namedtuple("Widget", "fn raw positional line")


WIDGETS = {}


def widget(name, raw=False, positional=None, line=False):
    """Декоратор: кладёт функцию в реестр под именем виджета."""
    def register(fn):
        WIDGETS[name] = Widget(fn, raw, positional, line)
        return fn
    return register


def render_widget(name, data, ctx, args=""):
    """html виджета или None, если такого виджета нет.

    data: словарь параметров (для raw-виджетов это строка с телом блока).
    ctx: объект с методом inline(текст) -> безопасный html.
    """
    entry = WIDGETS.get(name)
    if not entry:
        return None
    return entry.fn(data, ctx, args) if entry.raw else entry.fn(data, ctx)


def _num(raw, default, lo, hi):
    """Число из параметра, зажатое в границы; мусор даёт default."""
    try:
        value = float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return f"{default:g}"
    if value != value:  # nan
        return f"{default:g}"
    return f"{max(lo, min(hi, value)):g}"


def _choice(raw, allowed, default):
    """Значение из списка допустимых; всё остальное даёт default."""
    value = (raw or "").strip().lower()
    return value if value in allowed else default


def _lines(text):
    """Непустые строки тела блока, не больше MAX_LINES."""
    rows = [line.strip() for line in (text or "").split("\n")]
    return [row for row in rows if row][:MAX_LINES]


def barcode_value(raw):
    """Значение для штрихкода: заглавные латинские буквы, цифры и - . $ / + % пробел."""
    return _BARCODE_ALLOWED.sub("", (raw or "").upper())[:BARCODE_MAX_LEN]


def _asset_urls(asset):
    """(адрес содержимого, адрес вьювера). Чего нет в urls.py, то None."""
    result = []
    for name in (ASSET_CONTENT_URL, ASSET_VIEWER_URL):
        try:
            result.append(reverse(name, args=[asset.public_id]))
        except NoReverseMatch:
            result.append(None)
    return tuple(result)


def resolve_asset(ref):
    """Адрес содержимого ассета по ссылке или None, если ассета нет."""
    asset = find_asset(ref)
    if asset is None:
        return None
    return _asset_urls(asset)[0]


def _human_size(size):
    if not size:
        return ""
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024


def _menu(raw):
    """«Главная | Мир | Город» -> список пунктов (до MENU_MAX_ITEMS)."""
    items = [part.strip() for part in (raw or "").split("|")]
    return [item for item in items if item][:MENU_MAX_ITEMS]


MAX_GALLERY = 24          # картинок в галерее


MAX_FILES = 24            # файлов в группе


GALLERY_COLS = (1, 2, 3, 4)


MAP_MODES = ("political", "physical")


_ARG = re.compile(r'([a-z_][a-z0-9_]*)=(".*?"|\S+)')


def _head_args(args):
    """«cols=2 caption="Архив"» из строки открытия raw-виджета -> словарь."""
    return {m.group(1): m.group(2).strip('"') for m in _ARG.finditer(args or "")}


def _src_lines(text, limit):
    """Строки «src | подпись» -> [(src, подпись)]."""
    rows = []
    for line in _lines(text)[:limit]:
        src, _, caption = line.partition("|")
        if src.strip():
            rows.append((src.strip(), caption.strip()))
    return rows
