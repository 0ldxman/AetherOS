"""Виджеты для разметки: готовые части документа, которые вставляются блоком

    ::widget letterhead
    org: Департамент человеческой стабильности
    title: Отчёт о происшествии
    number: HS-0047-2024
    date: 13.05.2024
    barcode: HS-0047-2024
    ::

Виджет описан здесь, в коде: на входе только простые текстовые параметры
(строки «ключ: значение»), на выходе готовый html. Все значения экранируются.
Чтобы добавить виджет, достаточно написать функцию с декоратором @widget("имя").
"""

import re
from html import escape

WIDGETS = {}

# Code 39: шрифт Libre Barcode 39 рисует штрихи по символам *ТЕКСТ*
_BARCODE_ALLOWED = re.compile(r"[^A-Z0-9 .$/+%-]")
BARCODE_MAX_LEN = 40


def widget(name):
    def register(fn):
        WIDGETS[name] = fn
        return fn
    return register


def render_widget(name, params):
    """html виджета или None, если такого виджета нет."""
    fn = WIDGETS.get(name)
    return fn(params) if fn else None


def barcode_value(raw):
    """Значение для штрихкода: заглавные латинские буквы, цифры и - . $ / + % пробел."""
    return _BARCODE_ALLOWED.sub("", (raw or "").upper())[:BARCODE_MAX_LEN]


def _barcode_html(value):
    value = barcode_value(value)
    if not value:
        return ""
    return (
        '<div class="widget widget--barcode">'
        f'<span class="barcode-bars">*{value}*</span>'
        f'<span class="barcode-text">{value}</span>'
        "</div>"
    )


@widget("barcode")
def barcode(params):
    return _barcode_html(params.get("value")) or '<div class="widget widget--barcode"></div>'


@widget("letterhead")
def letterhead(params):
    def part(cls, key, prefix=""):
        value = params.get(key, "").strip()
        return f'<div class="{cls}">{prefix}{escape(value)}</div>' if value else ""

    main = part("lh-org", "org") + part("lh-title", "title")
    side = (
        part("lh-number", "number", "№ ")
        + part("lh-date", "date")
        + _barcode_html(params.get("barcode"))
    )
    return (
        '<header class="widget widget--letterhead">'
        f'<div class="lh-main">{main}</div>'
        f'<div class="lh-side">{side}</div>'
        "</header>"
    )