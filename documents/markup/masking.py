"""Замазка закрытого содержимого.

Часть пакета documents.markup (описание синтаксиса: documents/markup/__init__.py).
"""

import re

from markdown_it.token import Token
from secure.access import satisfied

from documents.markup.constants import MASK_CHAR


# =========================================================
# Masking
# =========================================================

def _mask(text):

    return re.sub(
        r"\S",
        MASK_CHAR,
        text,
    )


def _mask_token(tok):
    """Замазывает всё, что показывает токен."""

    if tok.type in (
        "fence",
        "code_block",
    ):

        tok.content = _mask(
            tok.content
        )

        tok.info = ""


def _resolve_inline(
    tok,
    keys,
    masked,
):
    """
    Решает строчные спойлеры и замазывает закрытое.
    """

    children = []
    stack = []
    any_masked = masked

    for child in (
        tok.children or []
    ):

        if (
            child.type
            == "spoiler_inline_open"
        ):

            expr = child.meta.get(
                "expr"
            )

            ok = (
                not masked
                and expr is not None
                and satisfied(
                    expr,
                    keys,
                )
            )

            stack.append(
                masked
            )

            masked = not ok

            any_masked = (
                any_masked
                or masked
            )

            child.meta = {}

            child.attrSet(
                "class",
                "spoiler spoiler--inline spoiler--"
                + (
                    "masked"
                    if masked
                    else "open"
                ),
            )

            if masked:

                child.attrSet(
                    "aria-hidden",
                    "true",
                )

        elif (
            child.type
            == "spoiler_inline_close"
        ):

            masked = (
                stack.pop()
                if stack
                else masked
            )

        elif masked:

            if child.type in (
                "link_open",
                "link_close",
            ):

                continue

            if child.type == "image":

                child = Token(
                    "text",
                    "",
                    0,
                    content=_mask(
                        child.content
                    ),
                )

            elif child.type in (
                "text",
                "text_special",
                "code_inline",
            ):

                child.content = _mask(
                    child.content
                )

                child.markup = ""

        children.append(
            child
        )

    tok.children = children

    if any_masked:

        tok.content = _mask(
            tok.content
        )
