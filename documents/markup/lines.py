"""Общие помощники блочных правил: шаблоны открытия, нормализация отступов редактора, разбор строк.

Часть пакета documents.markup (описание синтаксиса: documents/markup/__init__.py).
"""

import re

from documents.widgets import WIDGETS

from documents.markup.constants import CONTAINERS


# =========================================================
# Блок ::spoiler
# =========================================================

_OPEN = re.compile(
    r"::spoiler(?:\s+(.*))?$"
)

_WIDGET_OPEN = re.compile(
    r"::([a-z][a-z0-9_]*)(?:\s+(.*))?$"
)


# =========================================================
# Нормализация отступов редактора
# =========================================================

_FENCE_OPEN = re.compile(
    r"^[ \t]*(```+|~~~+)"
)


def _normalize_editor_indentation(text):
    """
    Убирает ведущие пробелы и табы из обычных строк редактора.

    В редакторе Tab используется как визуальный отступ. Для Markdown
    это не должно автоматически означать `indented code block`.

    Например:

        обычный текст
        - пункт
        ::box
        текст
        ::

    и:

        \tобычный текст
        \t- пункт
        \t::box
        \tтекст
        \t::

    должны обрабатываться одинаково.

    Fenced code blocks сохраняются как есть:

        ```python
        \tdef test():
        \t    return True
        ```

    То есть внутри ``` / ~~~ отступы не меняются.
    """

    if not text:
        return text

    lines = text.splitlines(
        keepends=True
    )

    result = []

    in_fence = False
    fence_char = None
    fence_len = 0

    for line in lines:

        content = line.rstrip(
            "\r\n"
        )

        newline = line[
            len(content):
        ]

        fence = _FENCE_OPEN.match(
            content
        )

        if fence:

            marker = fence.group(1)

            char = marker[0]
            length = len(marker)

            if not in_fence:

                in_fence = True
                fence_char = char
                fence_len = length

                result.append(line)

                continue

            if (
                char == fence_char
                and length >= fence_len
            ):

                in_fence = False
                fence_char = None
                fence_len = 0

                result.append(line)

                continue

        if in_fence:

            result.append(line)

        else:

            result.append(
                content.lstrip(
                    " \t"
                )
                + newline
            )

    return "".join(result)


def _line(state, n):
    """
    Возвращает содержимое строки без внешнего whitespace.

    markdown-it хранит отступ отдельно в sCount/tShift.
    Поэтому здесь мы намеренно убираем и пробелы, и табы.

    Благодаря этому:

        ::stamp TEST

    и:

        \t::stamp TEST

    воспринимаются одинаково.
    """

    start = (
        state.bMarks[n]
        + state.tShift[n]
    )

    return state.src[
        start:state.eMarks[n]
    ].strip()


def _is_aether_directive_line(state, n):
    """
    Проверяет исходную строку до удаления отступа.

    Aether-директива может начинаться с любого количества
    пробелов или табов:

        ::stamp TEST
          ::stamp TEST
        \t::stamp TEST

    Обычный текст без :: сюда не попадает.
    """

    start = state.bMarks[n]
    end = state.eMarks[n]

    text = state.src[
        start:end
    ]

    return bool(
        re.match(
            r"^[ \t]*::[a-z][a-z0-9_]*(?:\s|$)",
            text,
        )
    )


def _is_aether_close_line(state, n):
    """
    Проверяет закрывающую строку Aether:

        ::
          ::
        \t::

    """

    start = state.bMarks[n]
    end = state.eMarks[n]

    text = state.src[
        start:end
    ]

    return bool(
        re.match(
            r"^[ \t]*::[ \t]*$",
            text,
        )
    )


def _widget_head(text):
    """Строка открытия виджета -> (имя, args, блочный ли)."""

    match = _WIDGET_OPEN.match(
        text
    )

    if not match:
        return None

    if match.group(1) == "spoiler":
        return None

    name = match.group(1)

    args = (
        match.group(2) or ""
    ).strip()

    entry = WIDGETS.get(name)

    is_line = bool(
        entry and entry.line
    )

    is_block = (
        name in CONTAINERS
        or bool(
            entry and entry.raw
        )
        or (
            not args
            and not is_line
        )
    )

    return (
        name,
        args,
        is_block,
    )


def _opens_block(text):
    """Строка открывает блок, которому нужна своя ::."""

    if _OPEN.match(text):
        return True

    head = _widget_head(text)

    return bool(
        head and head[2]
    )
