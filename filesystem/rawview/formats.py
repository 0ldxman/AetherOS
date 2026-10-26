"""Построение файла по формату из реестра (registry.py): сигнатура, блоки, пакет частей или текстовый шаблон."""
import hashlib
import html
import string

from filesystem.rawview import registry
from filesystem.rawview.noise import noise, stable

PLACEHOLDERS = (
    "body", "body_html", "who", "when", "ref", "src", "at", "title", "hash", "sender", "recipients", "subject", "date", "id",
)


class _Context(dict):
    def __missing__(self, key):
        return ""


def known(name):
    return registry.format_named(name) is not None


def magic(name):
    """Сигнатура формата (bytes) или пустые байты, если такого формата нет."""
    fmt = registry.format_named(name)
    return fmt.magic if fmt else b""


def has_image(name):
    """Есть ли у формата часть-картинка: ассет-картинка кладётся в неё, а не в тело."""
    fmt = registry.format_named(name)
    return bool(fmt) and any(part.source == "image" for part in fmt.parts)


def context(body, meta):
    """Подстановки шаблонов: тело и поля источника."""
    text = body.decode("utf-8", "replace")
    paragraphs = "".join(f"<p>{html.escape(p)}</p>\n" for p in text.split("\n\n") if p.strip())
    values = _Context({key: str(value) for key, value in (meta or {}).items() if isinstance(value, (str, int, float))})
    values.update(body=text, body_html=paragraphs, hash=hashlib.sha256(body).hexdigest()[:16])
    values.setdefault("who", "unknown")
    return values


def variants(body):
    """Как тело встречается в готовом файле (как есть и абзацами HTML): их закрывает шум у недоступного игроку источника."""
    found = []
    for text in (body, context(body, {})["body_html"].encode()):
        if text and text not in found:
            found.append(text)
    return found


def _part(part, body, meta, image, seed):
    if part.source == "body":
        return body
    if part.source == "image":
        return image if image is not None else noise(f"{seed}:{part.name}", max(256, min(8192, len(body) * 3)))
    if part.source == "template":
        return string.Formatter().vformat(part.value, (), context(body, meta)).encode()
    if part.source == "hex":
        return bytes.fromhex(part.value)
    if part.source == "noise":
        return noise(f"{seed}:{part.name}", int(part.value or 0))
    if part.source == "confidence":
        return bytes([70 + stable(f"{seed}:conf", 0, 29)])
    return b""


def build(name, body, meta=None, image=None, seed=""):
    """Файл формата name вокруг тела body (bytes) и полей meta. Незнакомый формат оставляет тело как есть."""
    fmt = registry.format_named(name)
    if fmt is None:
        return body

    if fmt.kind == "text":
        return string.Formatter().vformat(fmt.template, (), context(body, meta)).encode()

    if fmt.kind in ("chunks", "package"):
        parts = [(part.name.encode("ascii", "replace"), _part(part, body, meta, image, seed)) for part in fmt.parts]
        if fmt.kind == "chunks":
            return fmt.magic + b"".join(len(data).to_bytes(4, "big") + tag[:4].ljust(4, b" ") + data for tag, data in parts)

        offset = len(fmt.magic) + 2 + 16 * len(parts)
        table, blob = b"", b""
        for tag, data in parts:
            table += tag[:8].ljust(8, b"\0") + (offset + len(blob)).to_bytes(4, "big") + len(data).to_bytes(4, "big")
            blob += data
        return fmt.magic + len(parts).to_bytes(2, "big") + table + blob

    return fmt.magic + body


def header(name, length=16):
    """Первые байты файла формата name."""
    return build(name, b"", {})[:length]


def prefix(name):
    """Начало текстового формата до первой подстановки (по нему вьювер узнаёт такие файлы)."""
    fmt = registry.format_named(name)
    if fmt is None or fmt.kind != "text":
        return ""
    return fmt.template.split("{", 1)[0].replace("{{", "{")
