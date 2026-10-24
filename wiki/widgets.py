"""Виджеты разметки: готовые части документа (шаг 1: листовые виджеты).

Виджет вставляется блоком в любое место тела документа или инфобокса.
Здесь описаны только листовые виджеты: stamp, signature, barcode, log, checks,
masthead (шапка сайта), bar (полоса «сохранено из»), ассеты (asset, image,
audio, video, file), divider (разделитель), а также page (его html пуст:
листы и футеры собирает пакет wiki/markup).
Контейнеры (section, box, grid) целиком в пакете wiki/markup.

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

from django.urls import NoReverseMatch, reverse

from assets.services import asset_widget_kind, find_asset
from pathlib import PurePosixPath

TONES = ("red", "green", "blue", "grey")
ALIGNS = ("left", "center", "right")

MAX_LINES = 200           # сколько строк берём у log и checks
BARCODE_MAX_LEN = 40      # длина значения штрихкода

MENU_MAX_ITEMS = 12       # пунктов меню в шапке сайта

IMAGE_RATIOS = {"16:9": "16-9", "4:3": "4-3", "3:2": "3-2", "1:1": "1-1", "3:4": "3-4", "9:16": "9-16"}
ASSET_CONTENT_URL = "asset_viewer:content"
ASSET_VIEWER_URL = "asset_viewer:viewer"
DIVIDER_STYLES = ("line", "double", "dashed", "dotted", "thick", "stars")

# Ссылка на ассет (asset:slug, slug или UUID) разбирается в
# assets.services.find_asset. Внешние ссылки (http и т.д.) ассетом не становятся.

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


def render_widget(name, data, ctx, args=""):
    """html виджета или None, если такого виджета нет.

    data: словарь параметров (для raw-виджетов это строка с телом блока).
    ctx: объект с методом inline(текст) -> безопасный html.
    """
    entry = WIDGETS.get(name)
    if not entry:
        return None
    return entry.fn(data, ctx, args) if entry.raw else entry.fn(data, ctx)


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
def log(text, ctx, args=""):
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
def checks(text, ctx, args=""):
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


def _asset_missing(ref, text="ASSET NOT FOUND"):
    return (
        '<div class="widget widget--asset-missing">'
        f'<span class="asset-missing-text">{text}</span>'
        f'<span class="asset-missing-ref">{escape(ref)}</span></div>\n'
    )


def _asset_figure(kind, inner, params, ctx):
    """Общая обёртка: width, align, caption."""
    default_width = 100 if kind == "audio" else 60
    width = _num(params.get("width"), default_width, 10, 100)
    align = _choice(params.get("align"), ALIGNS, "center")
    caption = ""
    if params.get("caption"):
        caption = f'<figcaption class="asset-caption">{ctx.inline(params["caption"])}</figcaption>'
    return (
        f'<figure class="widget widget--{kind} widget--align-{align}" style="--w: {width}%">'
        f'{inner}{caption}</figure>\n'
    )


def _render_image(asset, urls, params, ctx):
    content, viewer = urls
    alt = params.get("alt") or asset.name
    img = (
        f'<img class="image-img" src="{escape(content, quote=True)}" '
        f'alt="{escape(alt, quote=True)}" loading="lazy">'
    )
    if viewer:
        # href работает и без JS; main.js перехватывает клик и открывает окно
        img = (
            f'<a class="image-link" href="{escape(viewer, quote=True)}" '
            f'data-asset-viewer="{escape(viewer, quote=True)}" '
            f'data-asset-title="{escape(asset.name, quote=True)}">{img}</a>'
        )
    return _asset_figure("image", f'<div class="image-frame">{img}</div>', params, ctx)



def _render_audio(asset, urls, params, ctx):
    title = ctx.inline(params.get("title") or asset.name)

    filename = getattr(asset, "filename", None) or asset.name
    extension = PurePosixPath(filename).suffix.lower() or "—"

    audio_url, viewer_url = urls
    audio_id = escape(str(asset.public_id), quote=True)
    audio_src = escape(audio_url, quote=True)
    viewer_title = escape(str(filename), quote=True)
    extension_html = escape(extension, quote=True)

    # viewer_url может быть None (нет маршрута), поэтому escape() без проверки упадёт
    if viewer_url:
        viewer_href = escape(viewer_url, quote=True)
        id_html = (
            f'<a class="audio-id-link" href="{viewer_href}" '
            f'data-asset-viewer="{viewer_href}" '
            f'data-asset-title="{viewer_title}">{audio_id}</a>'
        )
        viewer_attr = f' data-viewer-url="{viewer_href}"'
    else:
        id_html = audio_id
        viewer_attr = ""

    # Универсальная часть: её используют web, doc, rec, infobox
    plain = (
        f'<div class="audio-title">{title}</div>'
        f'<audio class="audio-el" controls preload="none" src="{audio_src}"></audio>'
    )

    # Карточка: только для scan
    card = (
        '<div class="audio-card">'
        '<div class="audio-card-field audio-card-field--title">'
        '<span class="audio-card-label">TITLE:</span>'
        f'<span class="audio-card-value audio-card-title">{title}</span></div>'
        '<div class="audio-card-meta">'
        '<div class="audio-card-field audio-card-field--id">'
        '<span class="audio-card-label">ID:</span>'
        f'<span class="audio-card-value">{id_html}</span></div>'
        '<div class="audio-card-field audio-card-field--type">'
        '<span class="audio-card-label">TYPE:</span>'
        f'<span class="audio-card-value">{extension_html}</span></div>'
        '<div class="audio-card-field audio-card-field--duration">'
        '<span class="audio-card-label">DURATION:</span>'
        '<span class="audio-card-value audio-duration">—:—</span></div>'
        '</div>'
        f'<div class="audio-card-waveform" data-audio-src="{audio_src}" '
        'aria-label="Осциллограмма аудиозаписи">'
        '<svg class="audio-waveform-svg" viewBox="0 0 600 72" '
        'preserveAspectRatio="none" aria-hidden="true"></svg></div>'
        '</div>'
    )

    figure = _asset_figure("audio", plain + card, params, ctx)

    # Метаданные для встроенного плеера (audio-widget.js)
    metadata = (
        f'data-file-name="{viewer_title}" '
        f'data-asset-id="{audio_id}"'
        f'{viewer_attr}'
    )

    return figure.replace(
        'class="widget widget--audio',
        f'{metadata} class="widget widget--audio',
        1,
    )

def _render_video(asset, urls, params, ctx):
    filename = getattr(asset, "name", None) or asset.name
    source_name = getattr(asset, "filename", None)
    ext = (PurePosixPath(source_name).suffix if source_name else "") or ".mp4"

    asset_id = asset.public_id
    content, viewer = urls

    inner = (
        f'<video class="video-el" controls preload="metadata" '
        f'src="{escape(content, quote=True)}"></video>'
    )

    figure = _asset_figure("video", inner, params, ctx)

    viewer_attr = (
        f' data-viewer-url="{escape(viewer, quote=True)}"'
        if viewer else ""
    )

    metadata = (
        f'data-file-name="{escape(str(filename + ext), quote=True)}" '
        f'data-asset-id="{escape(str(asset_id), quote=True)}"'
        f'{viewer_attr}'
    )

    figure = figure.replace(
        'class="widget widget--video',
        f'{metadata} class="widget widget--video',
        1,
    )

    return figure


def _render_file(asset, urls, params, ctx):
    content, viewer = urls
    label = ctx.inline(params.get("label") or asset.filename or asset.name)
    size = _human_size(asset.size)

    code = barcode_value(str(asset.public_id))
    real_id = escape(str(asset.public_id), quote=True)
    real_name = escape(str(asset.name or asset.filename), quote=True)
    code_attr = f' data-barcode="{code}" data-id="{real_id}"' if code else ""

    source_name = getattr(asset, "filename", None) or asset.name or ""
    ext = PurePosixPath(str(source_name)).suffix.lstrip(".").upper()
    tag = escape(f"[{ext}]" if ext else "[FILE]", quote=True)

    main = (
        f'<a class="file-main" href="{escape(content, quote=True)}" download '
        f'data-filename="{real_name}" data-tag="{tag}">{label}</a>'
    )
    dots = '<span class="file-dots"></span>'
    size_html = f'<span class="file-size">{size}</span>' if size else ""
    open_html = ""
    if viewer:
        v = escape(viewer, quote=True)
        open_html = (
            f'<a class="file-open" href="{v}" data-asset-viewer="{v}" '
            f'data-asset-title="{escape(asset.name, quote=True)}">Открыть</a>'
        )

    return (
        f'<div class="widget widget--file"{code_attr}>'
        f'{main}{dots}{size_html}{open_html}</div>\n'
    )


_ASSET_RENDERERS = {
    "image": _render_image,
    "audio": _render_audio,
    "video": _render_video,
    "file": _render_file,
}


def _asset_widget(params, ctx, forced=None):
    ref = (params.get("src") or "").strip()
    asset = find_asset(ref)
    if asset is None:
        return _asset_missing(ref)
    urls = _asset_urls(asset)
    if urls[0] is None:
        return _asset_missing(ref)
    kind = asset_widget_kind(asset)
    if forced and kind != forced:
        return _asset_missing(ref, "ASSET TYPE MISMATCH")
    return _ASSET_RENDERERS[kind](asset, urls, params, ctx)


@widget("asset", positional="src")
def asset(params, ctx):
    """Ассет любого вида: ::asset theme-01 caption="Тема". Вид выбирается по типу файла."""
    return _asset_widget(params, ctx)


@widget("audio", positional="src")
def audio(params, ctx):
    """::audio theme-01 title="Тема города" """
    return _asset_widget(params, ctx, "audio")


@widget("video", positional="src")
def video(params, ctx):
    """::video intro-01 width=80 caption="Вступление" """
    return _asset_widget(params, ctx, "video")


@widget("file", positional="src")
def file(params, ctx):
    """::file report-01 label="Отчёт (PDF)" """
    return _asset_widget(params, ctx, "file")


@widget("image", positional="src")
def image(params, ctx):
    """Картинка: src=slug или UUID, alt, caption, width (10-100, %),
    align (left/center/right), ratio (для рамки, если картинки нет).

    Если ассета нет или он не картинка, вместо неё рамка с подписью alt,
    как у непрогрузившейся картинки в сохранённой странице.
    """
    ref = (params.get("src") or "").strip()
    found = find_asset(ref)
    if found is not None and asset_widget_kind(found) == "image":
        urls = _asset_urls(found)
        if urls[0]:
            return _render_image(found, urls, params, ctx)

    alt = params.get("alt", "")
    ratio = IMAGE_RATIOS.get((params.get("ratio") or "").strip(), "16-9")
    shown = ctx.inline(alt) if alt else "NO IMAGE"
    inner = f'<div class="image-frame"><div class="image-missing image-ratio-{ratio}"><span>{shown}</span></div></div>'
    return _asset_figure("image", inner, params, ctx)


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

    Сам html не выводит: пакет wiki/markup делит документ на листы по этим виджетам
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



KV_FLAGS = ("border",)

def _flags(args, allowed=KV_FLAGS):
    return [w for w in (args or "").lower().split() if w in allowed]

def _split_first(line, sep):
    left, found, right = line.partition(sep)
    return (left.strip(), right.strip()) if found else ("", line.strip())

def _kv_class(name, args):
    return " ".join(["widget", f"widget--{name}"] + [f"widget--{name}-{f}" for f in _flags(args)])


@widget("kv", raw=True)
def kv(text, ctx, args=""):
    rows = []
    for line in _lines(text):
        key, value = _split_first(line, ":")
        rows.append(
            '<div class="kv-row">'
            f'<div class="kv-key">{ctx.inline(key)}</div>'
            f'<div class="kv-val">{ctx.inline(value)}</div></div>'
        )
    return f'<div class="{_kv_class("kv", args)}">' + "".join(rows) + "</div>\n"


@widget("kvm", raw=True)
def kvm(text, ctx, args=""):
    chunks, current = [], []
    for line in (text or "").split("\n"):
        if line.strip() == "--":
            chunks.append(current)
            current = []
        else:
            current.append(line.strip())
    chunks.append(current)

    rows = []
    for chunk in chunks[:MAX_LINES]:
        chunk = [x for x in chunk if x]
        if not chunk:
            continue
        key, first = _split_first(chunk[0], ":")
        value = "".join(
            f'<div class="kv-line">{ctx.inline(x)}</div>'
            for x in ([first] + chunk[1:]) if x
        )
        rows.append(
            '<div class="kv-row">'
            f'<div class="kv-key">{ctx.inline(key)}</div>'
            f'<div class="kv-val">{value}</div></div>'
        )
    return f'<div class="{_kv_class("kvm", args)}">' + "".join(rows) + "</div>\n"


@widget("timeline", raw=True)
def timeline(text, ctx, args=""):
    rows = []
    for line in _lines(text):
        date, event = _split_first(line, "|")
        rows.append(
            '<div class="tl-row">'
            f'<div class="tl-date">{ctx.inline(date)}</div>'
            '<div class="tl-dot"></div>'
            f'<div class="tl-text">{ctx.inline(event)}</div></div>'
        )
    return '<div class="widget widget--timeline">' + "".join(rows) + "</div>\n"