"""Блочные правила контейнеров ::section / ::box / ::fold / ::grid.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

import re

from wiki.markup.constants import BOX_FLAGS, CONTAINERS, GRID_MAX_CELLS, GRID_MAX_COLS, PARAM_MAX_LEN
from wiki.markup.lines import _is_aether_close_line, _is_aether_directive_line, _line, _opens_block, _widget_head
from wiki.markup.widget_rule import _ARG


# =========================================================
# Контейнеры ::section / ::box / ::fold / ::grid
# =========================================================

def _section_meta(args):
    """«01 | Заголовок» -> metadata."""

    if "|" in args:

        num, title = args.split(
            "|",
            1,
        )

    else:

        num = ""
        title = args

    return {
        "num": num.strip()[:8],
        "title": title.strip()[
            :PARAM_MAX_LEN
        ],
    }


def _fold_meta(args):

    words = args.split()

    is_open = (
        bool(words)
        and words[-1].lower()
        == "open"
    )

    if is_open:
        words = words[:-1]

    return {
        "title": " ".join(words)[
            :PARAM_MAX_LEN
        ],
        "open": is_open,
    }


def _box_meta(args):
    """Флаги оформления box."""

    flags = []

    for word in args.lower().split():

        if (
            word in BOX_FLAGS
            and word not in flags
        ):

            flags.append(
                word
            )

    return {
        "flags": flags,
    }


_SEP = re.compile(
    r"--(?:\s+(.*))?$"
)


def _grid_tracks(args):
    """cols=4 -> [1,1,1,1], cols=1,2,1 -> [1,2,1]."""

    match = re.search(
        r"cols=(\S+)",
        args,
    )

    parts = (
        match.group(1).split(",")
        if match
        else []
    )

    nums = [
        int(x)
        for x in parts
        if (
            x.isdigit()
            and 1 <= int(x) <= GRID_MAX_COLS
        )
    ]

    if (
        len(nums) != len(parts)
        or not nums
        or len(nums) > GRID_MAX_COLS
    ):

        return [1, 1]

    return (
        [1] * nums[0]
        if len(nums) == 1
        else nums
    )


def _grid_flags(args):

    return {
        "noborder":
            "noborder" in args.split(),
    }


def _cell_meta(
    sep_args,
    columns,
):
    """Параметры после --."""

    params = {
        m.group(1):
            m.group(2).strip('"')
        for m in _ARG.finditer(
            sep_args or ""
        )
    }

    span = params.get(
        "span",
        "1",
    )

    span = (
        max(
            1,
            min(
                columns,
                int(span),
            ),
        )
        if span.isdigit()
        else 1
    )

    return {
        "span": span,
        "label": params.get(
            "label",
            "",
        )[:PARAM_MAX_LEN],
    }


def _tokenize_range(
    state,
    a,
    b,
):
    """Разбирает строки [a, b)."""

    old_parent = state.parentType
    old_max = state.lineMax

    state.parentType = "container"
    state.lineMax = b

    state.md.block.tokenize(
        state,
        a,
        b,
    )

    state.parentType = old_parent
    state.lineMax = old_max


_CONTAINER_META = {
    "section": _section_meta,
    "box": _box_meta,
    "fold": _fold_meta,
}


def _container_rule(
    state,
    start,
    end,
    silent,
):
    """
    Контейнер может иметь отступ:

        ::section
            ::box
                text
            ::
        ::

    """

    line = _line(
        state,
        start,
    )

    head = _widget_head(
        line
    )

    if (
        head is None
        or head[0] not in CONTAINERS
    ):

        return False

    if not _is_aether_directive_line(
        state,
        start,
    ):

        return False

    if silent:
        return True

    name, args, _ = head

    depth = 1
    nxt = start + 1
    seps = []

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

        elif (
            depth == 1
            and _SEP.match(text)
        ):

            match = _SEP.match(
                text
            )

            seps.append(
                (
                    nxt,
                    match.group(1),
                )
            )

        nxt += 1

    closed = nxt < end

    if name == "grid":

        _push_grid(
            state,
            start,
            nxt,
            args,
            seps,
        )

    else:

        token = state.push(
            name + "_open",
            "div",
            1,
        )

        token.block = True
        token.markup = (
            "::" + name
        )

        token.map = [
            start,
            nxt,
        ]

        token.meta = (
            _CONTAINER_META[name](
                args
            )
        )

        _tokenize_range(
            state,
            start + 1,
            nxt,
        )

        token = state.push(
            name + "_close",
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


def _push_grid(
    state,
    start,
    close,
    args,
    seps,
):
    tracks = _grid_tracks(
        args
    )

    cells = []

    a = start + 1
    sep_args = ""

    for i, (
        line,
        params,
    ) in enumerate(seps):

        if (
            i == 0
            and line == start + 1
        ):

            sep_args = params
            a = line + 1
            continue

        cells.append(
            (
                sep_args,
                a,
                line,
            )
        )

        sep_args = params
        a = line + 1

    if (
        a < close
        or cells
        or sep_args
    ):

        cells.append(
            (
                sep_args,
                a,
                close,
            )
        )

    token = state.push(
        "grid_open",
        "div",
        1,
    )

    token.block = True
    token.markup = "::grid"

    token.map = [
        start,
        close,
    ]

    token.meta = {
        "tracks": tracks,
        "flags": _grid_flags(
            args
        ),
    }

    for (
        sep_args,
        a,
        b,
    ) in cells[:GRID_MAX_CELLS]:

        token = state.push(
            "cell_open",
            "div",
            1,
        )

        token.block = True

        token.meta = _cell_meta(
            sep_args,
            len(tracks),
        )

        _tokenize_range(
            state,
            a,
            b,
        )

        token = state.push(
            "cell_close",
            "div",
            -1,
        )

        token.block = True

    token = state.push(
        "grid_close",
        "div",
        -1,
    )

    token.block = True
    token.markup = "::"
