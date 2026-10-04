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
"""

import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

from secure.access import satisfied

# варианты оформления: у инфобокса свой стиль, у основного текста свой
VARIANTS = ("body", "infobox")

# чем замазывается закрытый текст
MASK_CHAR = "█"

EXPR_MAX_LEN = 200


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
        if _OPEN.match(text):
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


def _mask(text):
    return re.sub(r"\S", MASK_CHAR, text)


def _mask_token(tok):
    """Замазывает всё, что показывает токен: текст, адреса, подписи."""
    if tok.type == "inline":
        children = []
        for child in tok.children or []:
            if child.type in ("link_open", "link_close"):
                continue  # адрес ссылки тоже секрет
            if child.type == "image":
                child = Token("text", "", 0, content=_mask(child.content))
            elif child.type in ("text", "text_special", "code_inline"):
                child.content = _mask(child.content)
                child.markup = ""
            children.append(child)
        tok.children = children
        tok.content = _mask(tok.content)
    elif tok.type in ("fence", "code_block"):
        tok.content = _mask(tok.content)
        tok.info = ""  # язык кода тоже подсказка


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
        else:
            if masked:
                _mask_token(tok)
            items.append((tok, masked))
    return items


def render(text, keys=frozenset(), variant="body"):
    """Превращает markdown в html, обёрнутый в <div class="md md--вариант">.

    keys: набор slug'ов ключей игрока; по ним решается, какие ::spoiler открыты.
    """
    if variant not in VARIANTS:
        raise ValueError(f"Неизвестный вариант оформления: {variant!r}")
    tokens = [tok for tok, _ in _process(text, keys)]
    html = _md.renderer.render(tokens, _md.options, {})
    return f'<div class="md md--{variant}">{html}</div>'


def _inline_plain(tok):
    parts = []
    for child in tok.children or []:
        if child.type in ("text", "text_special", "code_inline"):
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