"""Строчный спойлер [текст]{условие}.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

from markdown_it.helpers import parseLinkLabel

from wiki.markup.expr import SpoilerSyntaxError, parse_expr


# =========================================================
# Строчный спойлер
# =========================================================

def _inline_spoiler_rule(
    state,
    silent,
):
    src = state.src
    start = state.pos

    if src[start] != "[":
        return False

    label_end = parseLinkLabel(
        state,
        start,
    )

    if (
        label_end < 0
        or src[
            label_end + 1:
            label_end + 2
        ] != "{"
    ):

        return False

    brace_end = src.find(
        "}",
        label_end + 2,
        state.posMax,
    )

    if (
        brace_end < 0
        or "\n" in src[
            label_end + 2:
            brace_end
        ]
    ):

        return False

    if not silent:

        try:

            expr = parse_expr(
                src[
                    label_end + 2:
                    brace_end
                ]
            )

        except SpoilerSyntaxError:

            expr = None

        old_max = state.posMax

        token = state.push(
            "spoiler_inline_open",
            "span",
            1,
        )

        token.markup = "[]{}"

        token.meta = {
            "expr": expr,
        }

        state.pos = (
            start + 1
        )

        state.posMax = label_end

        state.md.inline.tokenize(
            state
        )

        state.posMax = old_max

        token = state.push(
            "spoiler_inline_close",
            "span",
            -1,
        )

        token.markup = "[]{}"

    state.pos = (
        brace_end + 1
    )

    return True
