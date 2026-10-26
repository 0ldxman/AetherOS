"""Форматы файлов: настоящие (по сигнатуре) и свои у Aether (scan, doc, snp, rec).

Свои форматы устроены по-разному, как у разных авторов:
    scan  блоки с метками (IMG, OCR, CONF): картинка и распознанный текст;
    doc   пакет частей с таблицей в начале (body, style, meta);
    snp   «слепок сайта»: HTML, который начинается комментарием-пометкой <!--SNP;
    rec   текст с пометкой §rec и блоком полей.
"""
import hashlib
import html

from filesystem.rawview.noise import noise, stable

AETHER_FORMATS = ("scan", "doc", "snp", "rec")

REAL_SIGNATURES = {
    "pdf": b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n",
    "png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
    "jpg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00",
    "gif": b"GIF89a",
    "zip": b"PK\x03\x04",
    "gz": b"\x1f\x8b\x08\x00",
    "wav": b"RIFF\x24\x08\x00\x00WAVEfmt ",
    "mp3": b"ID3\x04\x00\x00",
}

SCAN_MAGIC = b"\x9eSCAN\r\n\x1b"
DOC_MAGIC = b"\xd0\x0cDOC\x00"
PAK_MAGIC = b"\x8fPAK\r\n\x1a\x00"        # заголовок архива (слой archive)
APP_MAGIC = b"\x9bAPP\r\n\x1a\x00"        # дескриптор приложения


def known(name):
    return name in AETHER_FORMATS or name in REAL_SIGNATURES


def _chunk(tag, data):
    return len(data).to_bytes(4, "big") + tag + data


def _digest(body):
    return hashlib.sha256(body).hexdigest()[:16]


def build(fmt, body, meta=None, image=None, seed=""):
    """Контейнер формата fmt вокруг тела body (bytes) и полей meta. Настоящий формат (pdf, png...) это его сигнатура и тело."""
    meta = meta or {}

    if fmt == "rec":
        head = f"§rec\nwho: {meta.get('who', 'unknown')}\nwhen: {meta.get('when', '')}\nref: {meta.get('ref', '')}\n---\n"
        return head.encode() + body + b"\n"

    if fmt == "snp":
        text = body.decode("utf-8", "replace")
        paragraphs = "".join(f"<p>{html.escape(p)}</p>\n" for p in text.split("\n\n") if p.strip())
        sealed = _digest(body)
        page = (
            f"<!--SNP\nsrc:  {meta.get('src', '')}\nat:   {meta.get('at', '')}\nhash: {sealed}\n-->\n"
            f"<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>{html.escape(str(meta.get('title', '')))}</title>"
            f"<style>body{{font-family:serif}}</style></head>\n<body>\n{paragraphs}"
            f"<script>document.documentElement.dataset.snapshot=1</script>\n</body></html>\n"
            f"<!--@hdr HTTP/1.1 200 OK\ncontent-type: text/html; charset=utf-8\n-->\n<!--@seal {sealed} -->\n"
        )
        return page.encode()

    if fmt == "scan":
        picture = image if image is not None else noise(seed + ":img", max(256, min(8192, len(body) * 3)))
        confidence = bytes([70 + stable(seed + ":conf", 0, 29)])
        return SCAN_MAGIC + _chunk(b"IMG ", picture) + _chunk(b"OCR ", body) + _chunk(b"CONF", confidence)

    if fmt == "doc":
        parts = [
            ("body", body),
            ("style", b"font: serif; size: 11\n"),
            ("meta", f"title: {meta.get('title', '')}\nwhen: {meta.get('when', '')}\n".encode()),
        ]
        offset = len(DOC_MAGIC) + 2 + 16 * len(parts)
        table, blob = b"", b""
        for name, data in parts:
            table += name.encode().ljust(8, b"\0") + (offset + len(blob)).to_bytes(4, "big") + len(data).to_bytes(4, "big")
            blob += data
        return DOC_MAGIC + len(parts).to_bytes(2, "big") + table + blob

    signature = REAL_SIGNATURES.get(fmt)
    if signature is not None:
        return signature + body

    return body


def header(fmt, length=16):
    """Первые байты файла формата fmt (для сообщения об ошибке cvt)."""
    return build(fmt, b"", {})[:length]
