"""Публичный api: render() и visible_text().

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

from wiki.markup.constants import VARIANTS
from wiki.markup.engine import _md
from wiki.markup.pages import _render_sheets, _split_sheets
from wiki.markup.process import _process


# =========================================================
# Public API
# =========================================================

def render(
    text,
    keys=frozenset(),
    variant="body",
):
    """
    Превращает markdown в HTML.
    """

    if variant not in VARIANTS:

        raise ValueError(
            f"Неизвестный вариант оформления: "
            f"{variant!r}"
        )

    tokens = [
        tok
        for tok, _
        in _process(
            text,
            keys,
        )
    ]

    if variant == "body":

        html = _render_sheets(
            _split_sheets(tokens),
            keys,
        )

    else:

        html = _md.renderer.render(
            tokens,
            _md.options,
            {
                "keys": keys,
            },
        )

    return (
        f'<div class="md md--{variant}">'
        f'{html}'
        f'</div>'
    )


# =========================================================
# Search / visible text
# =========================================================

def _inline_plain(tok):

    parts = []

    stack = []

    hidden = 0

    for child in (
        tok.children or []
    ):

        if (
            child.type
            == "spoiler_inline_open"
        ):

            closed = (
                "spoiler--masked"
                in (
                    child.attrGet(
                        "class"
                    )
                    or ""
                )
            )

            stack.append(
                closed
            )

            hidden += closed

        elif (
            child.type
            == "spoiler_inline_close"
        ):

            hidden -= (
                stack.pop()
                if stack
                else 0
            )

        elif hidden:

            continue

        elif child.type in (
            "text",
            "text_special",
            "code_inline",
        ):

            parts.append(
                child.content
            )

        elif child.type == "image":

            parts.append(
                child.content
            )

        elif child.type in (
            "softbreak",
            "hardbreak",
        ):

            parts.append(
                "\n"
            )

    return "".join(
        parts
    )


def visible_text(
    text,
    keys=frozenset(),
):
    """
    Простой текст записи без разметки
    и без закрытых спойлеров.
    """

    parts = []

    for tok, masked in _process(
        text,
        keys,
    ):

        if masked:
            continue

        if tok.type == "inline":

            parts.append(
                _inline_plain(
                    tok
                )
            )

        elif tok.type in (
            "fence",
            "code_block",
        ):

            parts.append(
                tok.content
            )

    return "\n".join(
        p
        for p in parts
        if p
    )
