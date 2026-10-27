"""Текст записи вики так, как он лежит в готовом файле, а не в виде разметки вики.

В файле нет синтаксиса движка (::map ..., ::section ...): виджеты и блоки превращаются в то, что у
формата есть на их месте. Закрытые игроку спойлеры уже замазаны разбором разметки.

    text    простой текст; виджет остаётся короткой меткой [map: Внешняя]        (rec и всё, что не названо ниже)
    html    HTML страницы; виджет становится фигурой или блоком                  (snp)
    object  текст, а виджет встроенным объектом {object map "Внешняя"}           (doc)
    ocr     то, что прочитал бы сканер: печатный текст и подписи без объектов    (scan)
"""
import html
import re
import shlex

from wiki.markup.api import _inline_plain
from wiki.markup.engine import _md
from wiki.markup.process import _process

STYLES = ("text", "html", "object", "ocr")

# для каких форматов тело берётся не простым текстом
BODY_STYLE = {"doc": "object", "scan": "ocr"}

_BLOCKS = {
    "paragraph", "heading", "bullet_list", "ordered_list", "list_item", "blockquote",
    "table", "thead", "tbody", "tr", "th", "td",
}
_LEAVES = {"inline", "fence", "code_block", "hr", "html_block", "widget"}
_SPOILER_CLASS = re.compile(r' class="spoiler[^"]*"')
_ASSET_WIDGETS = {"asset", "image", "audio", "video", "file", "gallery", "files"}


def _params(data, args):
    """Параметры виджета: готовый словарь одностроччного или «ключ=значение» из строки открытия."""
    if isinstance(data, dict):
        return {key: str(value) for key, value in data.items()}
    try:
        words = shlex.split(args or "")
    except ValueError:
        words = (args or "").split()
    found = {}
    for word in words:
        key, sep, value = word.partition("=")
        found[key if sep else "_"] = value if sep else word
    return found


def _label(name, params, body):
    """Что у виджета читается человеком: подпись, текст, значение."""
    if name == "stamp":
        return params.get("text", "")
    if name == "signature":
        return " ".join(part for part in (params.get("name"), params.get("role")) if part)
    if name == "barcode":
        return params.get("value", "")
    if name in ("log", "checks"):
        return (body or "").strip()
    if name in ("masthead", "bar"):
        return params.get("name") or params.get("url") or params.get("_", "")
    if name in ("divider", "page"):
        return ""
    return params.get("caption") or params.get("alt") or params.get("title") or params.get("src") or params.get("_", "")


def _widget(style, name, data, args):
    params = _params(data, args)
    body = data if isinstance(data, str) else ""
    label = _label(name, params, body)

    if style == "object":
        return f'{{object {name} "{label}"}}' if label else f"{{object {name}}}"

    if style == "ocr":
        return "" if name in _ASSET_WIDGETS else label   # картинка в OCR не читается

    if style == "html":
        text = html.escape(label)
        if name in ("divider", "page"):
            return "<hr>\n"
        if name in ("log", "checks"):
            return f"<pre>{text}</pre>\n"
        if name in _ASSET_WIDGETS and params.get("src") and name in ("image", "asset"):
            return f'<img src="{html.escape(params["src"])}" alt="{html.escape(params.get("alt", ""))}">\n'
        if name == "map":
            return f'<figure data-kind="map"><figcaption>{text}</figcaption></figure>\n'
        return f'<figure data-kind="{html.escape(name)}"><figcaption>{text}</figcaption></figure>\n'

    return f"[{name}: {label}]" if label else f"[{name}]"


def _is_wrapper(tok):
    """Свой блок вики (section, box, grid, cell, spoiler): у готового файла такой обёртки нет."""
    kind = tok.type
    if kind in _LEAVES:
        return False
    return kind.endswith(("_open", "_close")) and kind.rsplit("_", 1)[0] not in _BLOCKS


def _section_title(tok):
    meta = tok.meta or {}
    return " ".join(str(meta[key]) for key in ("num", "title") if meta.get(key))


def _text(tokens, style):
    """Простой текст: блоки через пустую строку, списки чёрточками."""
    lines, current, lists = [], "", []

    def flush():
        nonlocal current
        if current.strip():
            lines.append(current.rstrip())
        current = ""

    for tok in tokens:
        kind = tok.type
        if kind == "widget":
            flush()
            meta = tok.meta
            text = _widget(style, meta["name"], meta.get("data"), meta.get("args"))
            if text:
                lines += [text, ""]
        elif kind == "inline":
            current += _inline_plain(tok)
        elif kind in ("fence", "code_block"):
            flush()
            lines.append(tok.content.rstrip())
        elif kind == "hr":
            flush()
            lines.append("---")
        elif kind in ("bullet_list_open", "ordered_list_open"):
            flush()
            lists.append([kind == "ordered_list_open", 0])
        elif kind in ("bullet_list_close", "ordered_list_close"):
            if lists:
                lists.pop()
            lines.append("")
        elif kind == "list_item_open" and lists:
            flush()
            lists[-1][1] += 1
            current = ("%d. " % lists[-1][1]) if lists[-1][0] else "- "
        elif kind in ("paragraph_close", "heading_close", "list_item_close", "td_close", "th_close", "tr_close"):
            if kind in ("td_close", "th_close"):
                current += " | "
            else:
                flush()
                if kind in ("paragraph_close", "heading_close") and not lists:
                    lines.append("")
        elif kind == "section_open":
            flush()
            if _section_title(tok):
                lines.append(_section_title(tok))
        elif kind == "blockquote_open":
            current = "> "

    flush()
    return "\n".join(lines).strip() + "\n" if lines else ""


def _html(tokens, keys):
    """HTML страницы: обычные блоки рисует тот же markdown, виджеты и обёртки заменены."""
    out, run = [], []

    def emit():
        if run:
            out.append(_SPOILER_CLASS.sub("", _md.renderer.render(run, _md.options, {"keys": keys})))
            run.clear()

    for tok in tokens:
        if tok.type == "widget":
            emit()
            meta = tok.meta
            out.append(_widget("html", meta["name"], meta.get("data"), meta.get("args")))
        elif _is_wrapper(tok):
            if tok.type == "section_open" and _section_title(tok):
                emit()
                out.append(f"<h2>{html.escape(_section_title(tok))}</h2>\n")
        else:
            run.append(tok)

    emit()
    return "".join(out)


def flatten(text, keys, style):
    """Тело записи вики в виде style (см. STYLES), строкой."""
    tokens = [tok for tok, _ in _process(text or "", keys)]
    if style == "html":
        return _html(tokens, keys)
    return _text([tok for tok in tokens if not _is_wrapper(tok) or tok.type == "section_open"], style)


def views(text, keys):
    """Все виды тела записи: {style: bytes}."""
    return {style: flatten(text, keys, style).encode() for style in STYLES}
