"""Блочное правило ::spoiler.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

from wiki.markup.expr import SpoilerSyntaxError, parse_expr
from wiki.markup.lines import _OPEN, _is_aether_close_line, _is_aether_directive_line, _line, _opens_block


# =========================================================
# Блок ::spoiler
# =========================================================

def _spoiler_rule(
    state,
    start,
    end,
    silent,
):
    """
    Aether spoiler.

    Эта rule зарегистрирована перед стандартным
    markdown-it правилом `code`.

    Дополнительно весь текст до markdown-it нормализуется
    через _normalize_editor_indentation(), поэтому Tab
    редактора больше не превращает строку в indented code.
    """

    match = _OPEN.match(
        _line(
            state,
            start,
        )
    )

    if not match:
        return False

    if not _is_aether_directive_line(
        state,
        start,
    ):
        return False

    if silent:
        return True

    try:
        expr = parse_expr(
            match.group(1)
        )

    except SpoilerSyntaxError:

        expr = None

    depth = 1
    nxt = start + 1

    while nxt < end:

        text = _line(
            state,
            nxt,
        )

        if _opens_block(text):

            depth += 1

        elif _is_aether_close_line(
            state,
            nxt,
        ):

            depth -= 1

            if depth == 0:
                break

        nxt += 1

    closed = nxt < end

    token = state.push(
        "spoiler_open",
        "div",
        1,
    )

    token.block = True
    token.markup = "::spoiler"

    token.map = [
        start,
        nxt,
    ]

    token.meta = {
        "expr": expr,
    }

    old_parent = state.parentType
    old_max = state.lineMax

    state.parentType = "container"
    state.lineMax = nxt

    state.md.block.tokenize(
        state,
        start + 1,
        nxt,
    )

    state.parentType = old_parent
    state.lineMax = old_max

    token = state.push(
        "spoiler_close",
        "div",
        -1,
    )

    token.block = True
    token.markup = "::"

    state.line = (
        nxt + 1
        if closed
        else nxt
    )

    return True
