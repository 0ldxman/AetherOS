"""Построение файла по формату из реестра (registry.py): сигнатура, блоки, пакет частей или текстовый шаблон."""
import hashlib
import html
import json
import string
import struct
import zlib

from filesystem.rawview import flatten, registry
from filesystem.rawview.noise import noise, stable

PLACEHOLDERS = (
    "body", "body_html", "body_xml", "body_json", "body_csv", "body_rtf", "body_b64", "who", "when", "ref", "src", "at", "title", "hash", "sender", "recipients", "subject", "date", "id",
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


def _rtf(text):
    """Текст для RTF: служебные знаки и всё не-ASCII (\\uN?) экранируются, переносы строк становятся \\par."""
    out = []
    for char in text:
        if char in "\\{}":
            out.append("\\" + char)
        elif char == "\n":
            out.append("\\par\n")
        elif ord(char) > 126:
            code = ord(char) if ord(char) < 32768 else ord(char) - 65536
            out.append(f"\\u{code}?")
        else:
            out.append(char)
    return "".join(out)


def _b64(body):
    import base64

    text = base64.b64encode(body).decode()
    return "\n".join(text[i:i + 64] for i in range(0, len(text), 64))


def context(body, meta, views=None):
    """Подстановки шаблонов: тело и поля источника. views (запись вики) даёт тело текстом и HTML без разметки вики."""
    views = views or {}
    text = views.get("text", body).decode("utf-8", "replace")
    paragraphs = views["html"].decode() if "html" in views else "".join(
        f"<p>{html.escape(p)}</p>\n" for p in text.split("\n\n") if p.strip()
    )
    values = _Context({key: str(value) for key, value in (meta or {}).items() if isinstance(value, (str, int, float))})
    values.update(
        body=text,
        body_html=paragraphs,
        body_xml=html.escape(text, quote=False),
        body_json=json.dumps(text, ensure_ascii=False)[1:-1],
        body_csv=text.replace('"', '""'),
        body_rtf=_rtf(text),
        body_b64=_b64(body),
        hash=hashlib.sha256(body).hexdigest()[:16],
    )
    values.setdefault("who", "unknown")
    return values


def variants(body, views=None):
    """Как тело встречается в готовом файле (как есть, абзацами HTML и видами записи): их закрывает шум у недоступного игроку источника."""
    found = []
    derived = context(body, {}, views)
    for text in (body, *(derived[key].encode() for key in ("body_html", "body_xml", "body_json", "body_csv", "body_rtf", "body_b64")),
                 *(views or {}).values()):
        if text and text not in found:
            found.append(text)
    return found


def _part(part, body, meta, image, seed, views=None, name=""):
    if part.source == "body":
        return (views or {}).get(flatten.BODY_STYLE.get(name, "text"), body)
    if part.source == "image":
        return image if image is not None else noise(f"{seed}:{part.name}", max(256, min(8192, len(body) * 3)))
    if part.source == "template":
        return string.Formatter().vformat(part.value, (), context(body, meta, views)).encode()
    if part.source == "hex":
        return bytes.fromhex(part.value)
    if part.source == "noise":
        return noise(f"{seed}:{part.name}", int(part.value or 0))
    if part.source == "confidence":
        return bytes([70 + stable(f"{seed}:conf", 0, 29)])
    return b""


def build(name, body, meta=None, image=None, seed="", views=None):
    """Файл формата name вокруг тела body (bytes) и полей meta. Незнакомый формат оставляет тело как есть."""
    fmt = registry.format_named(name)
    if fmt is None:
        return body

    if fmt.kind == "text":
        return string.Formatter().vformat(fmt.template, (), context(body, meta, views)).encode()

    if fmt.kind == "zip":
        return _zip([(part.name, _part(part, body, meta, image, seed, views, name)) for part in fmt.parts])

    if fmt.kind in ("chunks", "package"):
        parts = [(part.name.encode("ascii", "replace"), _part(part, body, meta, image, seed, views, name)) for part in fmt.parts]
        if fmt.kind == "chunks":
            return fmt.magic + b"".join(len(data).to_bytes(4, "big") + tag[:4].ljust(4, b" ") + data for tag, data in parts)

        offset = len(fmt.magic) + 2 + 16 * len(parts)
        table, blob = b"", b""
        for tag, data in parts:
            table += tag[:8].ljust(8, b"\0") + (offset + len(blob)).to_bytes(4, "big") + len(data).to_bytes(4, "big")
            blob += data
        return fmt.magic + len(parts).to_bytes(2, "big") + table + blob

    return fmt.magic + body


def _zip(files):
    """Настоящий zip без сжатия: заголовки файлов, центральный каталог, конец каталога."""
    stamp = ((2026 - 1980) << 9 | 10 << 5 | 26, 12 << 11)          # дата 2026-10-26 12:00, один раз на все файлы
    body, directory = b"", b""
    for path, data in files:
        raw = path.encode()
        crc = zlib.crc32(data) & 0xFFFFFFFF
        local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, stamp[1], stamp[0], crc, len(data), len(data), len(raw), 0)
        directory += struct.pack(
            "<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, stamp[1], stamp[0], crc, len(data), len(data),
            len(raw), 0, 0, 0, 0, 0, len(body),
        ) + raw
        body += local + raw + data
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(files), len(files), len(directory), len(body), 0)
    return body + directory + end


def header(name, length=16):
    """Первые байты файла формата name."""
    return build(name, b"", {})[:length]


def prefix(name):
    """Начало текстового формата до первой подстановки (по нему вьювер узнаёт такие файлы)."""
    fmt = registry.format_named(name)
    if fmt is None or fmt.kind != "text":
        return ""
    return fmt.template.split("{", 1)[0].replace("{{", "{")
