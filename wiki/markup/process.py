"""Обработка токенов: спойлеры, замазка, виджеты.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

from secure.access import satisfied

from wiki.markup.engine import _md
from wiki.markup.lines import _normalize_editor_indentation
from wiki.markup.masking import _mask_token, _resolve_inline


# =========================================================
# Token processing
# =========================================================

def _process(
    text,
    keys,
):
    """
    Токены с пометкой замазанности:
    [(токен, замазан)].

    Перед markdown-it текст проходит через
    _normalize_editor_indentation(), чтобы Tab,
    вставленный редактором, не превращал обычный Markdown
    в indented code block.
    """

    text = _normalize_editor_indentation(
        text or ""
    )

    items = []

    parents = []

    masked = False

    for tok in _md.parse(
        text
    ):

        if tok.type == "spoiler_open":

            expr = tok.meta.get(
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

            parents.append(
                masked
            )

            masked = not ok

            tok.meta = {}

            tok.attrSet(
                "class",
                "spoiler spoiler--"
                + (
                    "masked"
                    if masked
                    else "open"
                ),
            )

            if masked:

                tok.attrSet(
                    "aria-hidden",
                    "true",
                )

            items.append(
                (tok, masked)
            )

        elif tok.type == "spoiler_close":

            items.append(
                (tok, masked)
            )

            masked = (
                parents.pop()
            )

        elif tok.type in (
            "section_open",
            "box_open",
            "grid_open",
            "cell_open",
            "fold_open",
        ):

            if masked:

                tok.meta = {
                    "masked": True
                }

            items.append(
                (tok, masked)
            )

        elif tok.type == "widget":

            if masked:

                tok.meta = {
                    "masked": True
                }

                tok.markup = ""

            items.append(
                (tok, masked)
            )

        elif tok.type == "inline":

            _resolve_inline(
                tok,
                keys,
                masked,
            )

            items.append(
                (tok, masked)
            )

        else:

            if masked:

                _mask_token(
                    tok
                )

            items.append(
                (tok, masked)
            )

    return items
