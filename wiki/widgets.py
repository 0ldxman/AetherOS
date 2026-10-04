"""Виджеты разметки: готовые части документа (шаг 1: листовые виджеты).

Виджет вставляется блоком в любое место тела документа или инфобокса.
Здесь описаны только листовые виджеты: stamp, signature, barcode, log, checks,
masthead (шапка сайта), bar (полоса «сохранено из»), image (картинка),
divider (разделитель), а также page (его html пуст: листы и футеры собирает
markup.py).
Контейнеры (section, box, grid) целиком в markup.py.

Как работает виджет: на входе простые данные, на выходе готовый html.
Любой пользовательский текст проходит через ctx.inline(текст): это даёт
inline-markdown и строчные спойлеры [текст]{условие}, а всё остальное
экранируется. Значения, которые попадают в атрибуты (tone, angle, align),
сначала проверяются по белому списку или превращаются в число.

Чтобы добавить виджет, достаточно написать функцию с декоратором @widget.
"""

import re
from collections import namedtuple
from html import escape

TONES = ("red", "green", "blue", "grey")
ALIGNS = ("left", "center", "right")

MAX_LINES = 200           # сколько строк берём у log и checks
BARCODE_MAX_LEN = 40      # длина значения штрихкода

MENU_MAX_ITEMS = 12       # пунктов меню в шапке сайта

IMAGE_RATIOS = {"16:9": "16-9", "4:3": "4-3", "3:2": "3-2", "1:1": "1-1", "3:4": "3-4", "9:16": "9-16"}
DIVIDER_STYLES = ("line", "double", "dashed", "dotted", "thick", "stars")

# Ссылка на картинку: asset:группа:группа:slug (до 5 частей).
# Любая другая ссылка (http и т.д.) картинкой не становится.
_ASSET_REF = re.compile(r"asset(?::[a-z0-9_-]{1,40}){1,5}")

# Code 39: шрифт Libre Barcode 39 рисует штрихи по символам *ТЕКСТ*
_BARCODE_ALLOWED = re.compile(r"[^A-Z0-9 .$/+%-]")


# =========================================================
# Реестр
# =========================================================

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


def render_widget(name, data, ctx):
    """html виджета или None, если такого виджета нет.

    data: словарь параметров (для raw-виджетов это строка с телом блока).
    ctx: объект с методом inline(текст) -> безопасный html.
    """
    entry = WIDGETS.get(name)
    return entry.fn(data, ctx) if entry else None


# =========================================================
# Помощники для значений
# =========================================================

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


def resolve_asset(ref):
    """Адрес картинки по ссылке asset:... или None, если картинки нет.

    Пока хранилища картинок нет, всегда None: виджет image рисует заглушку.
    Когда появится модель картинок, менять нужно только эту функцию.
    """
    return None


def _menu(raw):
    """«Главная | Мир | Город» -> список пунктов (до MENU_MAX_ITEMS)."""
    items = [part.strip() for part in (raw or "").split("|")]
    return [item for item in items if item][:MENU_MAX_ITEMS]


# =========================================================
# Виджеты
# =========================================================

@widget("stamp", positional="text")
def stamp(params, ctx):
    """Штамп: ::stamp СЕКРЕТНО tone=red angle=-6 align=right"""
    text = ctx.inline(params.get("text", ""))
    if not text:
        return ""
    tone = _choice(params.get("tone"), TONES, "red")
    align = _choice(params.get("align"), ALIGNS, "left")
    angle = _num(params.get("angle"), -8, -45, 45)
    return (
        f'<div class="widget widget--stamp widget--align-{align}">'
        f'<span class="stamp stamp--{tone}" style="--angle: {angle}deg">{text}</span>'
        "</div>\n"
    )


@widget("signature", positional="name")
def signature(params, ctx):
    """Подпись: name, role, date; sign - текст «от руки» (по умолчанию name)."""
    hand = params.get("sign") or params.get("name", "")
    parts = []
    if hand:
        parts.append(f'<div class="sig-hand">{ctx.inline(hand)}</div>')
    parts.append('<div class="sig-line"></div>')
    for key in ("name", "role", "date"):
        if params.get(key):
            parts.append(f'<div class="sig-{key}">{ctx.inline(params[key])}</div>')
    return '<div class="widget widget--signature">' + "".join(parts) + "</div>\n"


@widget("barcode", positional="value")
def barcode(params, ctx):
    """Штрихкод: ::barcode HS-0047-2024"""
    value = barcode_value(params.get("value"))
    if not value:
        return '<div class="widget widget--barcode"></div>\n'
    return (
        '<div class="widget widget--barcode">'
        f'<span class="barcode-bars">*{value}*</span>'
        f'<span class="barcode-text">{value}</span>'
        "</div>\n"
    )


# «ЧЧ:ММ:СС УРОВЕНЬ сообщение»
_LOG_LINE = re.compile(
    r"(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+(INFO|WARN|ERROR|OK|DEBUG)\s+(.*)$"
)


@widget("log", raw=True)
def log(text, ctx):
    """Терминальный лог. Строка без времени и уровня выводится как есть."""
    rows = []
    for line in _lines(text):
        m = _LOG_LINE.match(line)
        if m:
            time, level, message = m.groups()  # время и уровень - только из regex
            rows.append(
                f'<div class="log-line log-{level.lower()}">'
                f'<span class="log-time">{time}</span>'
                f'<span class="log-level">{level}</span>'
                f'<span class="log-msg">{ctx.inline(message)}</span></div>'
            )
        else:
            rows.append(
                '<div class="log-line log-plain">'
                f'<span class="log-msg">{ctx.inline(line)}</span></div>'
            )
    return '<div class="widget widget--log">' + "".join(rows) + "</div>\n"


# «[x] текст» отмечено, «[ ] текст» нет. Пробел после "]" обязателен:
# так "[x]{ключ}" остаётся строчным спойлером, а не чекбоксом.
_CHECK = re.compile(r"\[([ xX])\](?:\s+(.*))?$")


@widget("checks", raw=True)
def checks(text, ctx):
    """Чекбоксы: по одному на строку; строка без метки считается неотмеченной."""
    rows = []
    for line in _lines(text):
        m = _CHECK.match(line)
        on, label = (m.group(1) in "xX", m.group(2) or "") if m else (False, line)
        rows.append(
            f'<span class="check{" check--on" if on else ""}">'
            '<span class="check-box"></span>'
            f'<span class="check-label">{ctx.inline(label)}</span></span>'
        )
    return '<div class="widget widget--checks">' + "".join(rows) + "</div>\n"


@widget("masthead", positional="name")
def masthead(params, ctx):
    """Шапка сайта: name, tagline, date, menu «А | Б | В», active (номер пункта с 1).

    ::masthead Вестник Порта menu="Главная | Мир | Город" active=1 date="12 МАРТА 2041"
    """
    name = ctx.inline(params.get("name", ""))
    tagline = ctx.inline(params.get("tagline", ""))
    date = ctx.inline(params.get("date", ""))
    items = _menu(params.get("menu"))
    active = int(float(_num(params.get("active"), 0, 0, MENU_MAX_ITEMS)))

    top = []
    if name or tagline:
        title = f'<span class="mast-name">{name}</span>' if name else ""
        sub = f'<span class="mast-tagline">{tagline}</span>' if tagline else ""
        top.append(f'<div class="mast-title">{title}{sub}</div>')
    if date:
        top.append(f'<div class="mast-date">{date}</div>')

    parts = []
    if top:
        parts.append('<div class="mast-top">' + "".join(top) + "</div>")
    if items:
        cells = "".join(
            f'<span class="mast-item{" mast-item--active" if i == active else ""}">'
            f"{ctx.inline(item)}</span>"
            for i, item in enumerate(items, 1)
        )
        parts.append(f'<div class="mast-menu">{cells}</div>')
    return '<div class="widget widget--masthead">' + "".join(parts) + "</div>\n"


@widget("bar", positional="url")
def bar(params, ctx):
    """Полоса «сохранено из»: url, date, id, label (по умолчанию ARCHIVED).

    ::bar news.example/2041/03/12 date=2041-03-14 id=ARC-0092
    Адрес выводится текстом, не ссылкой: копия не кликается.
    """
    label = ctx.inline(params.get("label") or "ARCHIVED")
    cells = [f'<span class="bar-label">{label}</span>']
    for key in ("url", "date", "id"):
        if params.get(key):
            cells.append(f'<span class="bar-{key}">{ctx.inline(params[key])}</span>')
    return '<div class="widget widget--bar">' + "".join(cells) + "</div>\n"


@widget("image", positional="src")
def image(params, ctx):
    """Картинка: src=asset:группа:slug, alt, caption, width (10-100, %),
    align (left/center/right), ratio (16:9, 4:3, 3:2, 1:1, 3:4, 9:16).

    Пока картинок нет (см. resolve_asset), вместо неё рамка с подписью alt,
    как у непрогрузившейся картинки в сохранённой странице.
    """
    ref = (params.get("src") or "").strip()
    url = resolve_asset(ref) if _ASSET_REF.fullmatch(ref) else None
    alt = params.get("alt", "")
    width = _num(params.get("width"), 100, 10, 100)
    align = _choice(params.get("align"), ALIGNS, "center")
    ratio = IMAGE_RATIOS.get((params.get("ratio") or "").strip(), "16-9")

    if url:
        inner = f'<img class="image-img" src="{escape(url, quote=True)}" alt="{escape(alt, quote=True)}">'
    else:
        shown = ctx.inline(alt) if alt else "NO IMAGE"
        inner = f'<div class="image-missing image-ratio-{ratio}"><span>{shown}</span></div>'

    caption = ""
    if params.get("caption"):
        caption = f'<figcaption class="image-caption">{ctx.inline(params["caption"])}</figcaption>'
    return (
        f'<figure class="widget widget--image widget--align-{align}" style="--w: {width}%">'
        f'<div class="image-frame">{inner}</div>{caption}</figure>\n'
    )


@widget("divider", positional="label", line=True)
def divider(params, ctx):
    """Разделитель: label (необязательно), style (line, double, dashed, dotted, thick, stars).

    ::divider                           линия
    ::divider ПРОДОЛЖЕНИЕ style=dashed  пунктир с подписью по центру
    ::divider style=stars               * * *
    """
    style = _choice(params.get("style"), DIVIDER_STYLES, "line")
    label = ctx.inline(params.get("label", ""))
    if style == "stars":
        body = '<span class="divider-mark">* * *</span>'
    elif label:
        body = (
            '<span class="divider-line"></span>'
            f'<span class="divider-label">{label}</span>'
            '<span class="divider-line"></span>'
        )
    else:
        body = '<span class="divider-line"></span>'
    return f'<div class="widget widget--divider divider--{style}">{body}</div>\n'


@widget("page", positional="text", line=True)
def page(params, ctx):
    """Конец листа: ::page подпись {n}/{total}

    Сам html не выводит: markup.py делит документ на листы по этим виджетам
    и ставит подпись футером. Сюда виджет попадает, только если он вложен
    в контейнер или стоит в инфобоксе, и там он ничего не делает.
    """
    return ""


SITE_PRESETS = ("paper", "dark", "tabloid", "gov")
SITE_ACCENTS = ("red", "blue", "green", "orange", "grey")


@widget("site", positional="preset", line=True)
def site(params, ctx):
    """Пресет сайта: ::site dark accent=blue

    Ничего не показывает: только вешает классы, по которым web.css
    переключает палитру и шрифты (через :has на .doc--web).
    """
    preset = _choice(params.get("preset"), SITE_PRESETS, "paper")
    accent = _choice(params.get("accent"), SITE_ACCENTS, "")
    classes = f"widget widget--site site-preset--{preset}"
    if accent:
        classes += f" site-accent--{accent}"
    return f'<div class="{classes}"></div>\n'