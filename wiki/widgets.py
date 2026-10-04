"""Виджеты разметки: готовые части документа (шаг 1: листовые виджеты).

Виджет вставляется блоком в любое место тела документа или инфобокса.
Здесь описаны только листовые виджеты: stamp, signature, barcode, log, checks,
а также page (его html пуст: листы и футеры собирает markup.py).
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

TONES = ("red", "green", "blue", "grey")
ALIGNS = ("left", "center", "right")

MAX_LINES = 200           # сколько строк берём у log и checks
BARCODE_MAX_LEN = 40      # длина значения штрихкода

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


@widget("page", positional="text", line=True)
def page(params, ctx):
    """Конец листа: ::page подпись {n}/{total}

    Сам html не выводит: markup.py делит документ на листы по этим виджетам
    и ставит подпись футером. Сюда виджет попадает, только если он вложен
    в контейнер или стоит в инфобоксе, и там он ничего не делает.
    """
    return ""