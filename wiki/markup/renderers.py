"""Контекст виджетов и html-рендеры виджетов и контейнеров.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""

from html import escape

from wiki.widgets import render_widget

from .constants import FOLD_DEFAULT_TITLE
from .engine import _md
from .masking import _resolve_inline


# =========================================================
# Widget context
# =========================================================

class _Ctx:
    """Что виджет получает от разметки."""

    def __init__(self, keys):
        self.keys = keys

    def inline(self, text):

        tokens = _md.parseInline(
            text or "",
            {},
        )

        for tok in tokens:

            _resolve_inline(
                tok,
                self.keys,
                False,
            )

        return _md.renderer.render(
            tokens,
            _md.options,
            {},
        )


def _ctx(env):

    return _Ctx(
        env.get(
            "keys",
            frozenset(),
        )
    )


MASKED_WIDGET = (
    '<div class="widget widget--masked" '
    'aria-hidden="true"></div>\n'
)


def _render_widget_token(
    tokens,
    idx,
    options,
    env,
):
    meta = tokens[idx].meta

    if meta.get("masked"):
        return MASKED_WIDGET

    try:

        html = render_widget(
            meta["name"],
            meta["data"],
            _ctx(env),
            meta.get("args", ""),
        )

    except Exception:
        import logging
        logging.getLogger(__name__).exception("widget %s failed", meta["name"])
        return (
            '<div class="widget widget--error">'
            '</div>\n'
        )

    if html is None:

        return (
            '<div class="widget widget--unknown">'
            f'::{escape(meta["name"])}'
            '</div>\n'
        )

    return html


_md.renderer.rules["widget"] = (
    _render_widget_token
)


# =========================================================
# Container rendering
# =========================================================

def _render_section_open(
    tokens,
    idx,
    options,
    env,
):
    meta = tokens[idx].meta

    masked = bool(
        meta.get("masked")
    )

    head = ""

    if not masked:

        if meta.get("num"):

            head += (
                '<span class="section-num">'
                f'{escape(meta["num"])}'
                '</span>'
            )

        if meta.get("title"):

            head += (
                '<span class="section-title">'
                f'{_ctx(env).inline(meta["title"])}'
                '</span>'
            )

    head_html = (
        f'<div class="section-head">'
        f'{head}'
        f'</div>'
        if head
        else ""
    )

    cls = (
        "section section--masked"
        if masked
        else "section"
    )

    return (
        f'<div class="{cls}">'
        f'{head_html}'
        f'<div class="section-body">\n'
    )


def _render_box_open(
    tokens,
    idx,
    options,
    env,
):
    meta = tokens[idx].meta

    flags = (
        []
        if meta.get("masked")
        else meta.get("flags", [])
    )

    cls = " ".join(
        ["box"]
        + [
            f"box--{flag}"
            for flag in flags
        ]
    )

    return (
        f'<div class="{cls}">\n'
    )


def _render_fold_open(
    tokens,
    idx,
    options,
    env,
):
    meta = tokens[idx].meta

    if meta.get("masked"):

        return (
            '<details class="fold fold--masked" open>'
            '<summary class="fold-head"></summary>'
            '<div class="fold-body">\n'
        )

    title = _ctx(env).inline(
        meta.get("title")
        or FOLD_DEFAULT_TITLE
    )

    open_attr = (
        " open"
        if meta.get("open")
        else ""
    )

    return (
        f'<details class="fold"{open_attr}>'
        f'<summary class="fold-head">'
        f'{title}'
        f'</summary>'
        f'<div class="fold-body">\n'
    )


def _render_grid_open(
    tokens,
    idx,
    options,
    env,
):
    meta = tokens[idx].meta

    if meta.get("masked"):
        return '<div class="grid">\n'

    columns = " ".join(
        f"minmax(0, {w}fr)"
        for w in meta["tracks"]
    )

    classes = ["grid"]

    if meta.get(
        "flags",
        {},
    ).get("noborder"):

        classes.append(
            "grid--noborder"
        )

    class_attr = " ".join(
        classes
    )

    return (
        f'<div class="{class_attr}" '
        f'style="grid-template-columns: '
        f'{columns}">\n'
    )


def _render_cell_open(
    tokens,
    idx,
    options,
    env,
):
    meta = tokens[idx].meta

    if meta.get("masked"):
        return '<div class="cell">\n'

    style = (
        f' style="grid-column: span '
        f'{meta["span"]}"'
        if meta["span"] > 1
        else ""
    )

    label = ""

    if meta["label"]:

        label = (
            '<div class="cell-label">'
            f'{_ctx(env).inline(meta["label"])}'
            '</div>\n'
        )

    return (
        f'<div class="cell"{style}>\n'
        f'{label}'
    )


_md.renderer.rules["grid_open"] = (
    _render_grid_open
)

_md.renderer.rules["grid_close"] = (
    lambda tokens, idx, options, env:
        "</div>\n"
)

_md.renderer.rules["cell_open"] = (
    _render_cell_open
)

_md.renderer.rules["cell_close"] = (
    lambda tokens, idx, options, env:
        "</div>\n"
)

_md.renderer.rules["section_open"] = (
    _render_section_open
)

_md.renderer.rules["section_close"] = (
    lambda tokens, idx, options, env:
        "</div></div>\n"
)

_md.renderer.rules["box_open"] = (
    _render_box_open
)

_md.renderer.rules["box_close"] = (
    lambda tokens, idx, options, env:
        "</div>\n"
)

_md.renderer.rules["fold_open"] = (
    _render_fold_open
)

_md.renderer.rules["fold_close"] = (
    lambda tokens, idx, options, env:
        "</div></details>\n"
)
