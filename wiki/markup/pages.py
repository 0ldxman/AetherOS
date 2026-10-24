"""Разбиение документа на листы.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

import re

from .engine import _md
from .renderers import _Ctx


# =========================================================
# Pages
# =========================================================

_FOOTER_VARS = re.compile(
    r"(?<!\])\{(n|total)\}"
)


def _is_page(tok):
    """::page только на верхнем уровне."""

    return (
        tok.type == "widget"
        and tok.level == 0
        and tok.meta.get("name")
        == "page"
    )


def _split_sheets(tokens):
    """Токены -> листы."""

    sheets = []
    current = []

    for tok in tokens:

        if _is_page(tok):

            sheets.append(
                (
                    current,
                    tok.meta["data"].get(
                        "text",
                        "",
                    ),
                )
            )

            current = []

        else:

            current.append(
                tok
            )

    if current:

        sheets.append(
            (
                current,
                None,
            )
        )

    return sheets


def _render_sheets(
    sheets,
    keys,
):
    total = len(sheets)

    footer = ""

    out = []

    for number, (
        tokens,
        text,
    ) in enumerate(
        sheets,
        1,
    ):

        if text:

            footer = text

        body = _md.renderer.render(
            tokens,
            _md.options,
            {
                "keys": keys,
            },
        )

        foot = ""

        if footer:

            shown = _FOOTER_VARS.sub(
                lambda m:
                    str(
                        number
                        if m.group(1) == "n"
                        else total
                    ),
                footer,
            )

            foot = (
                '<div class="sheet-footer">'
                f'{_Ctx(keys).inline(shown)}'
                '</div>'
            )

        out.append(
            f'<div class="sheet">'
            f'<div class="sheet-body">'
            f'{body}'
            f'</div>'
            f'{foot}'
            f'</div>\n'
        )

    return "".join(out)
