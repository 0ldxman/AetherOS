"""Листовые виджеты: штамп, подпись, штрихкод, журнал, чеклист, шапка сайта, полоса, разделитель, страница, сайт, таблицы ключ-значение, таймлайн."""
import re

from documents.widgets.base import ALIGNS, DIVIDER_STYLES, MAX_LINES, MENU_MAX_ITEMS, TONES, _choice, _lines, _menu, _num, barcode_value, widget


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

    Сам html не выводит: пакет documents/markup делит документ на листы по этим виджетам
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
