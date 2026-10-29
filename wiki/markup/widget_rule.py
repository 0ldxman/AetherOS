"""Блочное правило ::widget.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

import re

from wiki.widgets import WIDGETS

from wiki.markup.constants import CONTAINERS, PARAM_MAX_LEN, RAW_MAX_LEN
from wiki.markup.lines import _is_aether_close_line, _is_aether_directive_line, _line, _widget_head


# =========================================================
# Блок ::widget
# =========================================================

_ARG = re.compile(
    r'([a-z_][a-z0-9_]*)=(".*?"|\S+)'
)

_KEY_LINE = re.compile(
    r"([a-z_][a-z0-9_]*)\s*:\s*(.*)$",
    re.IGNORECASE,
)


def _parse_args(
    args,
    positional,
):
    """Строка параметров виджета -> словарь."""

    params = {}

    def take(match):

        params[
            match.group(1)
        ] = (
            match.group(2)
            .strip('"')
            [:PARAM_MAX_LEN]
        )

        return ""

    rest = " ".join(
        _ARG.sub(
            take,
            args,
        ).split()
    )

    if (
        rest
        and positional
        and positional not in params
    ):

        params[positional] = (
            rest[:PARAM_MAX_LEN]
        )

    return params


def _parse_body(lines):
    """Строки «ключ: значение» -> словарь."""

    params = {}

    for line in lines:

        match = _KEY_LINE.match(
            line
        )

        if match:

            params[
                match.group(1).lower()
            ] = (
                match.group(2)
                .strip()
                [:PARAM_MAX_LEN]
            )

    return params


def _widget_rule(
    state,
    start,
    end,
    silent,
):
    """
    Разбор Aether widget.

    Aether widget может иметь любой отступ:

        ::stamp TEST

        \t::stamp TEST

        \t\t::stamp TEST

    """

    line = _line(
        state,
        start,
    )

    head = _widget_head(
        line
    )

    if head is None:
        return False

    if not _is_aether_directive_line(
        state,
        start,
    ):
        return False

    if silent:
        return True

    name, args, is_block = head

    if name in CONTAINERS:
        return False

    entry = WIDGETS.get(
        name
    )

    raw = bool(
        entry and entry.raw
    )

    body = []

    # Без закрывающей "::" забираем
    # только строку открытия.
    state.line = start + 1

    if is_block:

        close = start + 1

        while (
            close < end
            and not _is_aether_close_line(
                state,
                close,
            )
        ):

            body.append(
                _line(
                    state,
                    close,
                )
            )

            close += 1

        if close < end:

            state.line = (
                close + 1
            )

        else:

            body = []

    if raw:

        data = "\n".join(
            body
        )[:RAW_MAX_LEN]

    elif args:

        data = _parse_args(
            args,
            (
                entry.positional
                if entry
                else None
            ),
        )

    else:

        data = _parse_body(
            body
        )

    token = state.push(
        "widget",
        "",
        0,
    )

    token.block = True

    token.markup = (
        "::" + name
    )

    token.map = [
        start,
        state.line,
    ]

    token.meta = {
        "name": name,
        "data": data,
        "args": (
            args
            if raw
            else ""
        ),
    }

    return True
