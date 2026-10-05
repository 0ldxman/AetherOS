"""Markdown -> html для записей вики.

Шаг 1: обычный markdown. Сырой html в тексте отключён, поэтому автор записи
не может вставить скрипт или чужую разметку: всё, что похоже на тег,
выводится как текст.

Шаг 2: блок ::spoiler с условием по ключам игрока.

    ::spoiler key_a and (key_b or not key_c)
    Скрытый текст, **markdown** внутри работает.
    ::

Условие: slug ключа, and, or, not и скобки (приоритет: not, and, or).
Блоки можно вкладывать, внутренний открывается только если открыт внешний.

Закрытый блок отправляется игроку уже замазанным: каждый символ, кроме
пробелов и переносов, заменяется на MASK_CHAR, ссылки теряют адрес, картинки
и язык в блоках кода пропадают. Настоящего текста в html нет совсем.
Неверное условие, пустое условие и незакрытый блок закрывают доступ,
а не открывают.

Шаг 3: блок ::widget (виджеты из widgets.py). Блок записывается двумя способами:

    ::stamp СЕКРЕТНО tone=red angle=-6     одной строкой, "::" в конце не нужна

    ::signature                            блоком: параметры «ключ: значение»
    name: И. Иванов
    role: Директор
    ::

Правило: если в строке открытия есть параметры, блок однострочный; если их
нет, блок идёт до "::". Исключение: виджеты с raw=True (log, checks) всегда
идут блоком до "::", тело читается строками как есть. Незакрытый блок
забирает только строку открытия, остальной текст остаётся нетронутым.
Неизвестный виджет выводится приглушённой заглушкой, а не роняет страницу.
Виджет внутри закрытого спойлера выводится пустой заглушкой без имени и
параметров: штрихкод или номер документа не утекают мимо замазки.

Шаг 4: контейнеры (блоки, внутри которых обычный markdown, виджеты и другие
контейнеры). Закрываются строкой "::", как спойлер.

    ::section 01 | REFERENCE: 99078-AA6    номер | заголовок (номер необязателен)
    Текст раздела.
    ::

    ::box border center big                рамка и выравнивание флагами
    Текст.
    ::

Шаг 5: сетка ::grid. Ячейки разделяются строкой "--", у которой могут быть
параметры следующей ячейки: span=N (сколько колонок занять) и label="..."
(мелкая подпись над содержимым). Внутри ячейки обычная разметка.

    ::grid cols=4                  cols=N: N равных колонок; cols=1,2,1: веса
    Иванов                         первая ячейка (без параметров)
    -- label="AGENT NAME"          вторая ячейка с подписью
    [0451]{key_a}
    -- span=2
    Ячейка на две колонки
    ::

Строка, начинающаяся с "--" и пробела, внутри ::grid всегда разделитель
(кроме вложенных блоков: у них свои разделители). Если первая строка тела
сама "--", она не создаёт пустую ячейку, а задаёт параметры первой.

Шаг 6: листы. Виджет ::page одновременно заканчивает лист и задаёт его футер.

    Текст первого листа.
    ::page HS-0047-2024 · rev. 3 · стр. {n}/{total}

    Текст второго листа.
    ::page

{n} это номер листа, {total} число листов. Пустой ::page берёт футер
предыдущего, последний лист без своего ::page тоже. Если после последнего
::page текста нет, пустого листа не будет. ::page работает только на верхнем
уровне основного текста: внутри контейнеров, спойлеров и в инфобоксе
игнорируется (иначе рвётся вложенность). Основной текст (variant="body")
всегда выводится листами: <div class="sheet">; пустой документ листов не
имеет.

Шаг 7: строчный спойлер [текст]{условие}: то же условие, что у блочного, но
внутри строки (абзац, ячейка, список, заголовок, подпись виджета).

    Агент [Иванов]{key_a} прибыл в [сектор 12]{key_a and key_b}.

Закрытый фрагмент идёт в html замазанным (длина текста сохраняется), ссылки
и картинки внутри теряют адреса, в поиск он не попадает. Между "]" и "{"
пробела быть не должно, "{" без закрывающей "}" на той же строке остаётся
обычным текстом. Неверное условие в скобках закрывает фрагмент.

Флаги box: см. BOX_FLAGS, неизвестные игнорируются. Незакрытый контейнер идёт
до конца родителя. Заголовок и флаги контейнера в закрытом спойлере не
выводятся, а тело замазывается как обычно.
"""

import re
from html import escape

from markdown_it import MarkdownIt
from markdown_it.helpers import parseLinkLabel
from markdown_it.token import Token

from secure.access import satisfied
from wiki.widgets import WIDGETS, render_widget

# варианты оформления: у инфобокса свой стиль, у основного текста свой
VARIANTS = ("body", "infobox")

# чем замазывается закрытый текст
MASK_CHAR = "█"

EXPR_MAX_LEN = 200

# ограничения на данные виджетов
PARAM_MAX_LEN = 300   # длина одного значения параметра
RAW_MAX_LEN = 5000    # длина тела raw-виджета (log, checks)

# контейнеры: имена, у которых внутри обычная разметка (в WIDGETS их нет)
CONTAINERS = ("section", "box", "grid", "fold")
FOLD_DEFAULT_TITLE = "Подробнее"
GRID_MAX_COLS = 12
GRID_MAX_CELLS = 200
BOX_FLAGS = ("border", "dark", "center", "right", "small", "big", "bold", "muted", "flush")


# =========================================================
# Условие спойлера
# =========================================================

class SpoilerSyntaxError(ValueError):
    pass


_KEYWORDS = {"and", "or", "not"}
_SLUG = re.compile(r"[A-Za-z0-9_-]+")


def parse_expr(src):
    """Условие спойлера -> условие в формате secure/access.py.

    "a" -> "a"; "a and b" -> {"all": [...]}; "a or b" -> {"any": [...]};
    "not a" -> {"not": "a"}. Неверная запись: SpoilerSyntaxError.
    """
    src = (src or "").strip()
    if not src:
        raise SpoilerSyntaxError("Пустое условие.")
    if len(src) > EXPR_MAX_LEN:
        raise SpoilerSyntaxError("Слишком длинное условие.")

    words = src.replace("(", " ( ").replace(")", " ) ").split()
    pos = 0

    def peek():
        return words[pos] if pos < len(words) else None

    def take():
        nonlocal pos
        word = peek()
        pos += 1
        return word

    def parse_or():
        parts = [parse_and()]
        while peek() == "or":
            take()
            parts.append(parse_and())
        return parts[0] if len(parts) == 1 else {"any": parts}

    def parse_and():
        parts = [parse_not()]
        while peek() == "and":
            take()
            parts.append(parse_not())
        return parts[0] if len(parts) == 1 else {"all": parts}

    def parse_not():
        if peek() == "not":
            take()
            return {"not": parse_not()}
        return parse_atom()

    def parse_atom():
        word = take()
        if word is None:
            raise SpoilerSyntaxError("Условие оборвано.")
        if word == "(":
            inner = parse_or()
            if take() != ")":
                raise SpoilerSyntaxError("Нет закрывающей скобки.")
            return inner
        if word in _KEYWORDS or word == ")" or not _SLUG.fullmatch(word):
            raise SpoilerSyntaxError(f"Неожиданное слово: {word!r}.")
        return word

    result = parse_or()
    if pos != len(words):
        raise SpoilerSyntaxError(f"Лишнее слово: {words[pos]!r}.")
    return result


# =========================================================
# Блок ::spoiler
# =========================================================

_OPEN = re.compile(r"::spoiler(?:\s+(.*))?$")
_WIDGET_OPEN = re.compile(r"::([a-z][a-z0-9_]*)(?:\s+(.*))?$")


def _widget_head(text):
    """Строка открытия виджета -> (имя, строка параметров, блочный ли) или None.

    Блочный виджет закрывается строкой "::", однострочный нет. Блочный тот, у
    которого raw=True или в строке открытия нет параметров.
    """
    match = _WIDGET_OPEN.match(text)
    if not match or match.group(1) == "spoiler":
        return None
    name, args = match.group(1), (match.group(2) or "").strip()
    entry = WIDGETS.get(name)
    is_line = bool(entry and entry.line)
    is_block = name in CONTAINERS or bool(entry and entry.raw) or (not args and not is_line)
    return name, args, is_block


def _opens_block(text):
    """Строка открывает блок, которому нужна своя закрывающая "::"."""
    if _OPEN.match(text):
        return True
    head = _widget_head(text)
    return bool(head and head[2])


def _line(state, n):
    start = state.bMarks[n] + state.tShift[n]
    return state.src[start:state.eMarks[n]].strip()


def _spoiler_rule(state, start, end, silent):
    # четыре пробела отступа и больше: это блок кода, а не спойлер
    if state.sCount[start] - state.blkIndent >= 4:
        return False
    match = _OPEN.match(_line(state, start))
    if not match:
        return False
    if silent:
        return True

    try:
        expr = parse_expr(match.group(1))
    except SpoilerSyntaxError:
        expr = None  # закрыто для всех

    # ищем закрывающую "::" с учётом вложенных блоков
    depth = 1
    nxt = start + 1
    while nxt < end:
        text = _line(state, nxt)
        if _opens_block(text):
            depth += 1
        elif text == "::":
            depth -= 1
            if depth == 0:
                break
        nxt += 1
    closed = nxt < end  # незакрытый блок идёт до конца и замазывается весь

    token = state.push("spoiler_open", "div", 1)
    token.block = True
    token.markup = "::spoiler"
    token.map = [start, nxt]
    token.meta = {"expr": expr}

    old_parent, old_max = state.parentType, state.lineMax
    state.parentType = "container"
    state.lineMax = nxt
    state.md.block.tokenize(state, start + 1, nxt)
    state.parentType, state.lineMax = old_parent, old_max

    token = state.push("spoiler_close", "div", -1)
    token.block = True
    token.markup = "::"

    state.line = nxt + 1 if closed else nxt
    return True


# =========================================================
# Блок ::widget
# =========================================================

# именованный параметр в строке открытия: ключ=значение или ключ="значение с пробелами"
_ARG = re.compile(r'([a-z_][a-z0-9_]*)=("[^"]*"|\S+)')
# строка тела: «ключ: значение»
_KEY_LINE = re.compile(r"([a-z_][a-z0-9_]*)\s*:\s*(.*)$", re.IGNORECASE)


def _parse_args(args, positional):
    """Строка параметров в строке открытия -> словарь.

    "СЕКРЕТНО tone=red" -> {"tone": "red", "text": "СЕКРЕТНО"}, если у виджета
    positional="text". Слово без "ключ=" получает параметр positional.
    """
    params = {}

    def take(match):
        params[match.group(1)] = match.group(2).strip('"')[:PARAM_MAX_LEN]
        return ""

    rest = " ".join(_ARG.sub(take, args).split())
    if rest and positional and positional not in params:
        params[positional] = rest[:PARAM_MAX_LEN]
    return params


def _parse_body(lines):
    """Строки «ключ: значение» -> словарь. Строки другого вида пропускаются."""
    params = {}
    for line in lines:
        match = _KEY_LINE.match(line)
        if match:
            params[match.group(1).lower()] = match.group(2).strip()[:PARAM_MAX_LEN]
    return params


def _widget_rule(state, start, end, silent):
    if state.sCount[start] - state.blkIndent >= 4:
        return False
    head = _widget_head(_line(state, start))
    if head is None:
        return False
    if silent:
        return True

    name, args, is_block = head
    if name in CONTAINERS:
        return False  # это дело _container_rule
    entry = WIDGETS.get(name)
    raw = bool(entry and entry.raw)

    body = []
    state.line = start + 1  # без закрывающей "::" забираем только строку открытия
    if is_block:
        close = start + 1
        while close < end and _line(state, close) != "::":
            body.append(_line(state, close))
            close += 1
        if close < end:
            state.line = close + 1
        else:
            body = []

    if raw:
        data = "\n".join(body)[:RAW_MAX_LEN]
    elif args:
        data = _parse_args(args, entry.positional if entry else None)
    else:
        data = _parse_body(body)

    token = state.push("widget", "", 0)
    token.block = True
    token.markup = "::" + name
    token.map = [start, state.line]
    token.meta = {"name": name, "data": data, "args": args if raw else ""}
    return True


# =========================================================
# Контейнеры ::section и ::box
# =========================================================

def _section_meta(args):
    """«01 | Заголовок» -> {"num": "01", "title": "Заголовок"}; без "|" только заголовок."""
    if "|" in args:
        num, title = args.split("|", 1)
    else:
        num, title = "", args
    return {"num": num.strip()[:8], "title": title.strip()[:PARAM_MAX_LEN]}

def _fold_meta(args):
    words = args.split()
    is_open = bool(words) and words[-1].lower() == "open"
    if is_open:
        words = words[:-1]
    return {"title": " ".join(words)[:PARAM_MAX_LEN], "open": is_open}

def _box_meta(args):
    """Слова из BOX_FLAGS по порядку, без повторов; остальное игнорируется."""
    flags = []
    for word in args.lower().split():
        if word in BOX_FLAGS and word not in flags:
            flags.append(word)
    return {"flags": flags}


_SEP = re.compile(r"--(?:\s+(.*))?$")


def _grid_tracks(args):
    """cols=4 -> [1, 1, 1, 1]; cols=1,2,1 -> [1, 2, 1]; мусор или пусто -> [1, 1]."""
    match = re.search(r"cols=(\S+)", args)
    parts = match.group(1).split(",") if match else []
    nums = [int(x) for x in parts if x.isdigit() and 1 <= int(x) <= GRID_MAX_COLS]
    if len(nums) != len(parts) or not nums or len(nums) > GRID_MAX_COLS:
        return [1, 1]
    return [1] * nums[0] if len(nums) == 1 else nums

def _grid_flags(args):
    """Флаги оформления grid."""
    return {
        "noborder": "noborder" in args.split(),
    }


def _cell_meta(sep_args, columns):
    """Параметры после "--": span (зажат в 1..columns) и label."""
    params = {m.group(1): m.group(2).strip('"') for m in _ARG.finditer(sep_args or "")}
    span = params.get("span", "1")
    span = max(1, min(columns, int(span))) if span.isdigit() else 1
    return {"span": span, "label": params.get("label", "")[:PARAM_MAX_LEN]}


def _tokenize_range(state, a, b):
    """Разбирает строки [a, b) как отдельный кусок разметки."""
    old_parent, old_max = state.parentType, state.lineMax
    state.parentType = "container"
    state.lineMax = b
    state.md.block.tokenize(state, a, b)
    state.parentType, state.lineMax = old_parent, old_max

_CONTAINER_META = {"section": _section_meta, "box": _box_meta, "fold": _fold_meta}

def _container_rule(state, start, end, silent):
    if state.sCount[start] - state.blkIndent >= 4:
        return False
    head = _widget_head(_line(state, start))
    if head is None or head[0] not in CONTAINERS:
        return False
    if silent:
        return True

    name, args, _ = head

    # ищем закрывающую "::" с учётом вложенных блоков;
    # заодно запоминаем разделители "--" этого уровня (нужны только grid)
    depth = 1
    nxt = start + 1
    seps = []
    while nxt < end:
        text = _line(state, nxt)
        if _opens_block(text):
            depth += 1
        elif text == "::":
            depth -= 1
            if depth == 0:
                break
        elif depth == 1 and _SEP.match(text):
            seps.append((nxt, _SEP.match(text).group(1)))
        nxt += 1
    closed = nxt < end  # незакрытый контейнер идёт до конца родителя

    if name == "grid":
        _push_grid(state, start, nxt, args, seps)
    else:
        token = state.push(name + "_open", "div", 1)
        token.block = True
        token.markup = "::" + name
        token.map = [start, nxt]
        token.meta = _CONTAINER_META[name](args)
        _tokenize_range(state, start + 1, nxt)
        token = state.push(name + "_close", "div", -1)
        token.block = True
        token.markup = "::"

    state.line = nxt + 1 if closed else nxt
    return True


def _push_grid(state, start, close, args, seps):
    tracks = _grid_tracks(args)

    # ячейки: (параметры, первая строка, строка после последней)
    cells = []
    a, sep_args = start + 1, ""
    for i, (line, params) in enumerate(seps):
        if i == 0 and line == start + 1:
            sep_args, a = params, line + 1
            continue
        cells.append((sep_args, a, line))
        sep_args, a = params, line + 1

    if a < close or cells or sep_args:
        cells.append((sep_args, a, close))

    token = state.push("grid_open", "div", 1)
    token.block = True
    token.markup = "::grid"
    token.map = [start, close]
    token.meta = {
        "tracks": tracks,
        "flags": _grid_flags(args),
    }

    for sep_args, a, b in cells[:GRID_MAX_CELLS]:
        token = state.push("cell_open", "div", 1)
        token.block = True
        token.meta = _cell_meta(sep_args, len(tracks))
        _tokenize_range(state, a, b)

        token = state.push("cell_close", "div", -1)
        token.block = True

    token = state.push("grid_close", "div", -1)
    token.block = True
    token.markup = "::"


# =========================================================
# Строчный спойлер [текст]{условие}
# =========================================================

def _inline_spoiler_rule(state, silent):
    src, start = state.src, state.pos
    if src[start] != "[":
        return False

    label_end = parseLinkLabel(state, start)  # позиция "]" (вложенные скобки учтены)
    if label_end < 0 or src[label_end + 1:label_end + 2] != "{":
        return False
    brace_end = src.find("}", label_end + 2, state.posMax)
    if brace_end < 0 or "\n" in src[label_end + 2:brace_end]:
        return False

    if not silent:
        try:
            expr = parse_expr(src[label_end + 2:brace_end])
        except SpoilerSyntaxError:
            expr = None  # закрыто для всех

        old_max = state.posMax
        token = state.push("spoiler_inline_open", "span", 1)
        token.markup = "[]{}"
        token.meta = {"expr": expr}
        state.pos, state.posMax = start + 1, label_end
        state.md.inline.tokenize(state)
        state.posMax = old_max
        token = state.push("spoiler_inline_close", "span", -1)
        token.markup = "[]{}"

    state.pos = brace_end + 1
    return True


# =========================================================
# Разбор, замазка, вывод
# =========================================================

_md = (
    MarkdownIt("commonmark", {"html": False, "linkify": False})
    .enable("table")
    .enable("strikethrough")
)
_md.block.ruler.before(
    "fence",
    "spoiler",
    _spoiler_rule,
    {"alt": ["paragraph", "reference", "blockquote", "list"]},
)
_md.block.ruler.before(
    "fence",
    "widget",
    _widget_rule,
    {"alt": ["paragraph", "reference", "blockquote", "list"]},
)


_md.block.ruler.before(
    "fence",
    "container",
    _container_rule,
    {"alt": ["paragraph", "reference", "blockquote", "list"]},
)


_md.inline.ruler.before("link", "spoiler_inline", _inline_spoiler_rule)


class _Ctx:
    """Что виджет получает от разметки: inline-markdown без сырого html.

    Строчные спойлеры в тексте решаются по ключам игрока, как в основном тексте.
    """

    def __init__(self, keys):
        self.keys = keys

    def inline(self, text):
        tokens = _md.parseInline(text or "", {})
        for tok in tokens:
            _resolve_inline(tok, self.keys, False)
        return _md.renderer.render(tokens, _md.options, {})


def _ctx(env):
    return _Ctx(env.get("keys", frozenset()))

MASKED_WIDGET = '<div class="widget widget--masked" aria-hidden="true"></div>\n'


def _render_widget_token(tokens, idx, options, env):
    meta = tokens[idx].meta
    if meta.get("masked"):
        return MASKED_WIDGET
    try:
        html = render_widget(meta["name"], meta["data"], _ctx(env), meta.get("args", ""))
    except Exception:
        return '<div class="widget widget--error"></div>\n'  # сломанный виджет не роняет страницу
    if html is None:
        return f'<div class="widget widget--unknown">::{escape(meta["name"])}</div>\n'
    return html


_md.renderer.rules["widget"] = _render_widget_token


def _render_section_open(tokens, idx, options, env):
    meta = tokens[idx].meta
    masked = bool(meta.get("masked"))
    head = ""
    if not masked:  # заголовок закрытого раздела не выводится
        if meta.get("num"):
            head += f'<span class="section-num">{escape(meta["num"])}</span>'
        if meta.get("title"):
            head += f'<span class="section-title">{_ctx(env).inline(meta["title"])}</span>'
    head_html = f'<div class="section-head">{head}</div>' if head else ""
    cls = "section section--masked" if masked else "section"
    return f'<div class="{cls}">{head_html}<div class="section-body">\n'


def _render_box_open(tokens, idx, options, env):
    meta = tokens[idx].meta
    flags = [] if meta.get("masked") else meta.get("flags", [])
    cls = " ".join(["box"] + [f"box--{flag}" for flag in flags])
    return f'<div class="{cls}">\n'

def _render_fold_open(tokens, idx, options, env):
    meta = tokens[idx].meta
    if meta.get("masked"):
        return '<details class="fold fold--masked" open><summary class="fold-head"></summary><div class="fold-body">\n'
    title = _ctx(env).inline(meta.get("title") or FOLD_DEFAULT_TITLE)
    open_attr = " open" if meta.get("open") else ""
    return f'<details class="fold"{open_attr}><summary class="fold-head">{title}</summary><div class="fold-body">\n'

def _render_grid_open(tokens, idx, options, env):
    meta = tokens[idx].meta

    if meta.get("masked"):
        return '<div class="grid">\n'

    columns = " ".join(
        f"minmax(0, {w}fr)"
        for w in meta["tracks"]
    )

    classes = ["grid"]

    if meta.get("flags", {}).get("noborder"):
        classes.append("grid--noborder")

    class_attr = " ".join(classes)

    return (
        f'<div class="{class_attr}" '
        f'style="grid-template-columns: {columns}">\n'
    )


def _render_cell_open(tokens, idx, options, env):
    meta = tokens[idx].meta
    if meta.get("masked"):
        return '<div class="cell">\n'
    style = f' style="grid-column: span {meta["span"]}"' if meta["span"] > 1 else ""
    label = ""
    if meta["label"]:
        label = f'<div class="cell-label">{_ctx(env).inline(meta["label"])}</div>\n'
    return f'<div class="cell"{style}>\n{label}'


_md.renderer.rules["grid_open"] = _render_grid_open
_md.renderer.rules["grid_close"] = lambda tokens, idx, options, env: "</div>\n"
_md.renderer.rules["cell_open"] = _render_cell_open
_md.renderer.rules["cell_close"] = lambda tokens, idx, options, env: "</div>\n"
_md.renderer.rules["section_open"] = _render_section_open
_md.renderer.rules["section_close"] = lambda tokens, idx, options, env: "</div></div>\n"
_md.renderer.rules["box_open"] = _render_box_open
_md.renderer.rules["box_close"] = lambda tokens, idx, options, env: "</div>\n"
_md.renderer.rules["fold_open"] = _render_fold_open
_md.renderer.rules["fold_close"] = lambda tokens, idx, options, env: "</div></details>\n"


def _mask(text):
    return re.sub(r"\S", MASK_CHAR, text)


def _mask_token(tok):
    """Замазывает всё, что показывает токен: текст, адреса, подписи."""
    if tok.type in ("fence", "code_block"):
        tok.content = _mask(tok.content)
        tok.info = ""  # язык кода тоже подсказка


def _resolve_inline(tok, keys, masked):
    """Решает строчные спойлеры в inline-токене и замазывает закрытое.

    masked: замазан ли весь токен (он внутри закрытого блока). Внутри открытого
    блока замазывается только то, что в закрытых [..]{..}. Замазанное теряет
    текст, адреса ссылок и картинок.
    """
    children, stack, any_masked = [], [], masked
    for child in tok.children or []:
        if child.type == "spoiler_inline_open":
            expr = child.meta.get("expr")
            ok = not masked and expr is not None and satisfied(expr, keys)
            stack.append(masked)
            masked = not ok
            any_masked = any_masked or masked
            child.meta = {}
            child.attrSet("class", "spoiler spoiler--inline spoiler--" + ("masked" if masked else "open"))
            if masked:
                child.attrSet("aria-hidden", "true")
        elif child.type == "spoiler_inline_close":
            masked = stack.pop() if stack else masked
        elif masked:
            if child.type in ("link_open", "link_close"):
                continue  # адрес ссылки тоже секрет
            if child.type == "image":
                child = Token("text", "", 0, content=_mask(child.content))
            elif child.type in ("text", "text_special", "code_inline"):
                child.content = _mask(child.content)
                child.markup = ""
        children.append(child)
    tok.children = children
    if any_masked:
        tok.content = _mask(tok.content)


def _process(text, keys):
    """Токены с пометкой замазанности: [(токен, замазан)]."""
    items = []
    parents = []  # замазанность снаружи каждого открытого спойлера
    masked = False

    for tok in _md.parse(text or ""):
        if tok.type == "spoiler_open":
            expr = tok.meta.get("expr")
            ok = not masked and expr is not None and satisfied(expr, keys)
            parents.append(masked)
            masked = not ok
            tok.meta = {}
            tok.attrSet("class", "spoiler spoiler--" + ("masked" if masked else "open"))
            if masked:
                tok.attrSet("aria-hidden", "true")
            items.append((tok, masked))
        elif tok.type == "spoiler_close":
            items.append((tok, masked))
            masked = parents.pop()
        elif tok.type in ("section_open", "box_open", "grid_open", "cell_open", "fold_open"):
            if masked:
                tok.meta = {"masked": True}  # заголовок, флаги, подписи и раскладку не выводим
            items.append((tok, masked))
        elif tok.type == "widget":
            if masked:
                tok.meta = {"masked": True}  # имя и параметры тоже секрет
                tok.markup = ""
            items.append((tok, masked))
        elif tok.type == "inline":
            _resolve_inline(tok, keys, masked)
            items.append((tok, masked))
        else:
            if masked:
                _mask_token(tok)
            items.append((tok, masked))
    return items


_FOOTER_VARS = re.compile(r"(?<!\])\{(n|total)\}")


def _is_page(tok):
    """::page на верхнем уровне (внутри контейнеров level больше нуля)."""
    return tok.type == "widget" and tok.level == 0 and tok.meta.get("name") == "page"


def _split_sheets(tokens):
    """Токены -> [(токены листа, футер или None)]; пустой хвост листом не считается."""
    sheets, current = [], []
    for tok in tokens:
        if _is_page(tok):
            sheets.append((current, tok.meta["data"].get("text", "")))
            current = []
        else:
            current.append(tok)
    if current:
        sheets.append((current, None))
    return sheets


def _render_sheets(sheets, keys):
    total = len(sheets)
    footer = ""  # пустой ::page и последний лист берут футер предыдущего
    out = []
    for number, (tokens, text) in enumerate(sheets, 1):
        if text:
            footer = text
        body = _md.renderer.render(tokens, _md.options, {"keys": keys})
        foot = ""
        if footer:
            shown = _FOOTER_VARS.sub(
                lambda m: str(number if m.group(1) == "n" else total), footer
            )
            foot = f'<div class="sheet-footer">{_Ctx(keys).inline(shown)}</div>'
        out.append(f'<div class="sheet"><div class="sheet-body">{body}</div>{foot}</div>\n')
    return "".join(out)


def render(text, keys=frozenset(), variant="body"):
    """Превращает markdown в html, обёрнутый в <div class="md md--вариант">.

    keys: набор slug'ов ключей игрока; по ним решается, какие ::spoiler открыты.
    """
    if variant not in VARIANTS:
        raise ValueError(f"Неизвестный вариант оформления: {variant!r}")
    tokens = [tok for tok, _ in _process(text, keys)]
    if variant == "body":
        html = _render_sheets(_split_sheets(tokens), keys)
    else:
        html = _md.renderer.render(tokens, _md.options, {"keys": keys})
    return f'<div class="md md--{variant}">{html}</div>'


def _inline_plain(tok):
    parts, stack, hidden = [], [], 0  # hidden: сколько закрытых [..]{..} сейчас открыто
    for child in tok.children or []:
        if child.type == "spoiler_inline_open":
            closed = "spoiler--masked" in (child.attrGet("class") or "")
            stack.append(closed)
            hidden += closed
        elif child.type == "spoiler_inline_close":
            hidden -= stack.pop() if stack else 0
        elif hidden:
            continue
        elif child.type in ("text", "text_special", "code_inline"):
            parts.append(child.content)
        elif child.type == "image":
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append("\n")
    return "".join(parts)


def visible_text(text, keys=frozenset()):
    """Простой текст записи без разметки и без закрытых спойлеров.

    Для поиска: закрытый текст вырезан целиком, по нему ничего не найти.
    """
    parts = []
    for tok, masked in _process(text, keys):
        if masked:
            continue
        if tok.type == "inline":
            parts.append(_inline_plain(tok))
        elif tok.type in ("fence", "code_block"):
            parts.append(tok.content)
    return "\n".join(p for p in parts if p)