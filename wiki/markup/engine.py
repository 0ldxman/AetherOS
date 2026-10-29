"""Экземпляр markdown-it и регистрация Aether-правил.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

from markdown_it import MarkdownIt

from wiki.markup.container_rule import _container_rule
from wiki.markup.inline_rule import _inline_spoiler_rule
from wiki.markup.spoiler_rule import _spoiler_rule
from wiki.markup.widget_rule import _widget_rule


# =========================================================
# Markdown
# =========================================================

_md = (
    MarkdownIt(
        "commonmark",
        {
            "html": False,
            "linkify": False,
        },
    )
    .enable("table")
    .enable("strikethrough")
)


# =========================================================
# Aether block rules
#
# Они находятся перед `code`.
#
# Это дополнительная защита для Aether-разметки.
# Основная защита от Tab обычного Markdown выполняется
# через _normalize_editor_indentation().
# =========================================================

_md.block.ruler.before(
    "code",
    "spoiler",
    _spoiler_rule,
    {
        "alt": [
            "paragraph",
            "reference",
            "blockquote",
            "list",
        ],
    },
)


_md.block.ruler.before(
    "code",
    "widget",
    _widget_rule,
    {
        "alt": [
            "paragraph",
            "reference",
            "blockquote",
            "list",
        ],
    },
)


_md.block.ruler.before(
    "code",
    "container",
    _container_rule,
    {
        "alt": [
            "paragraph",
            "reference",
            "blockquote",
            "list",
        ],
    },
)


_md.inline.ruler.before(
    "link",
    "spoiler_inline",
    _inline_spoiler_rule,
)
