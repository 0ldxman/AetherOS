"""Ключи файла в его байтах: каждый ключ из FileKey лежит в файле блоком в стиле PEM, в своём месте.

    -----BEGIN ACCESS KEY-----
    Keyname: secret_a

    q3Fz8hT0... (стабильный base64-шум)
    -----END ACCESS KEY-----

Место зависит от контейнера и считается по (файл, слаг), поэтому не меняется между открытиями:
    jpg   сегмент COM между сегментами до начала изображения;   png   чанк tEXt между чанками;
    pdf   строки комментария после %%EOF;                       zip   комментарий архива (docx, xlsx, epub...);
    scan  чанк KEY между чанками;                               doc   часть key.pem в пакете;
    html, xml, svg   комментарий перед закрывающим тегом;       текст   в конце текста;
    остальное: у настоящих данных (ассет) в конце, у шума внутри на стабильном смещении.
Слои работают поверх: шифр, архив и прочие прячут блоки вместе с содержимым. Если источник закрыт игроку, на месте
блоков шум той же длины.
"""
import base64
import re
import struct
import zlib

from filesystem.rawview import registry
from filesystem.rawview.noise import noise, stable

LABEL = "ACCESS KEY"
BEGIN = f"-----BEGIN {LABEL}-----"
END = f"-----END {LABEL}-----"
BLOCK = re.compile(rf"{re.escape(BEGIN)}\r?\nKeyname: ([A-Za-z0-9_.:-]{{1,64}})\r?\n(?:\r?\n)?[A-Za-z0-9+/=\r\n]*{re.escape(END)}")

PNG = b"\x89PNG\r\n\x1a\n"


def slugs_of(machine_file):
    """Слаги ключей файла по порядку."""
    return sorted(machine_file.keys.values_list("key__slug", flat=True))


def armor(slug, seed):
    """Блок ключа: шапка со слагом и шум, на вид как сертификат."""
    raw = noise(f"{seed}:{slug}:body", stable(f"{seed}:{slug}:len", 48, 120))
    text = base64.b64encode(raw).decode()
    lines = "\n".join(text[i:i + 64] for i in range(0, len(text), 64))
    return f"{BEGIN}\nKeyname: {slug}\n\n{lines}\n{END}\n".encode()


def parse(data, offset):
    """Ключ (слаг), блок которого начинается ровно с offset, или None."""
    text = data[offset:offset + 4096].decode("ascii", "ignore")
    found = BLOCK.match(text)
    return found.group(1) if found else None


def _pick(seed, slug, count):
    return stable(f"{seed}:{slug}:slot", 0, max(0, count - 1))


def _insert(data, inserts):
    """Вставить куски в позиции (позиции в исходных байтах); длины растут сзади, поэтому сначала дальние."""
    for position, piece in sorted(inserts, key=lambda item: -item[0]):
        data = data[:position] + piece + data[position:]
    return data


def _jpeg(data, blocks, seed):
    positions, pos = [2], 2
    while pos + 4 <= len(data) and data[pos] == 0xFF and data[pos + 1] not in (0xD9, 0xDA):
        pos += 2 + struct.unpack(">H", data[pos + 2:pos + 4])[0]
        positions.append(pos)
    if data[pos:pos + 2] != b"\xff\xda":
        return None
    inserts = []
    for slug, block in blocks:
        body = block + b"\x00"
        inserts.append((positions[_pick(seed, slug, len(positions))], b"\xff\xfe" + struct.pack(">H", len(body) + 2) + body))
    return _insert(data, inserts)


def _png(data, blocks, seed):
    positions, pos = [], 8
    while pos + 12 <= len(data):
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        if data[pos + 4:pos + 8] == b"IEND":
            positions.append(pos)
            break
        pos += 12 + size
        positions.append(pos)
    else:
        return None
    positions = [p for p in positions if p > 8 + 25 - 1] or positions
    inserts = []
    for slug, block in blocks:
        body = b"Comment\x00" + block
        chunk = struct.pack(">I", len(body)) + b"tEXt" + body + struct.pack(">I", zlib.crc32(b"tEXt" + body) & 0xFFFFFFFF)
        inserts.append((positions[_pick(seed, slug, len(positions))], chunk))
    return _insert(data, inserts)


def _pdf(data, blocks, seed):
    return data + b"".join(b"%" + line.encode() + b"\n" if line else b"%\n" for slug, block in blocks
                           for line in block.decode().rstrip("\n").split("\n"))


def _zip(data, blocks, seed):
    end = data.rfind(b"PK\x05\x06")
    if end < 0 or len(data) - end < 22 or data[end + 20:end + 22] != b"\x00\x00":
        return None
    comment = b"".join(block for _, block in blocks)[:65535]
    return data[:end + 20] + struct.pack("<H", len(comment)) + data[end + 22:] + comment


def _chunks(data, blocks, seed, fmt):
    head = len(fmt.magic)
    positions, pos = [head], head
    while pos + 8 <= len(data):
        pos += 8 + int.from_bytes(data[pos:pos + 4], "big")
        positions.append(pos)
    if pos != len(data):
        return None
    inserts = [(positions[_pick(seed, slug, len(positions))], len(block).to_bytes(4, "big") + b"KEY " + block)
               for slug, block in blocks]
    return _insert(data, inserts)


def _package(data, blocks, seed, fmt):
    head = len(fmt.magic)
    count = int.from_bytes(data[head:head + 2], "big")
    table = [(data[head + 2 + i * 16:head + 10 + i * 16], int.from_bytes(data[head + 10 + i * 16:head + 14 + i * 16], "big"),
              int.from_bytes(data[head + 14 + i * 16:head + 18 + i * 16], "big")) for i in range(count)]
    start = head + 2 + count * 16
    parts = [(tag.rstrip(b"\0"), data[offset:offset + size]) for tag, offset, size in table]
    parts.append((b"key.pem", b"".join(block for _, block in blocks)))
    offset = head + 2 + 16 * len(parts)
    index, blob = b"", b""
    for tag, content in parts:
        index += tag[:8].ljust(8, b"\0") + (offset + len(blob)).to_bytes(4, "big") + len(content).to_bytes(4, "big")
        blob += content
    return data[:head] + len(parts).to_bytes(2, "big") + index + blob if start <= len(data) else None


def _markup(data, blocks, seed):
    text = data.decode("utf-8")
    spot = text.rfind("</body>")
    spot = text.rfind("</") if spot < 0 else spot
    if spot < 0:
        return None
    comment = "".join(f"<!--\n{block.decode()}-->\n" for _, block in blocks)
    return (text[:spot] + comment + text[spot:]).encode()


def _text(data, blocks, seed):
    text = data.decode("utf-8")
    return (text.rstrip("\n") + "\n\n" + "\n".join(block.decode() for _, block in blocks)).encode()


def _anywhere(data, blocks, seed, real):
    """Неизвестный контейнер: настоящие данные не трогаем, блоки кладём в конец; шум принимает их внутри."""
    if real:
        return data + b"".join(block for _, block in blocks)
    inserts = [(stable(f"{seed}:{slug}:at", len(data) // 4, max(len(data) // 4, len(data) * 3 // 4)), block) for slug, block in blocks]
    return _insert(data, inserts)


def _registered(data):
    """Формат реестра с видом chunks или package, которому принадлежит начало данных."""
    return next((item for item in registry.all_formats() if item.kind in ("chunks", "package") and item.magic and data.startswith(item.magic)), None)


def embed(data, slugs, seed, real=False, locked=False):
    """Байты data с блоками ключей slugs. locked: блоки заменены шумом той же длины. real: данные настоящие (ассет)."""
    if not slugs:
        return data
    blocks = [(slug, armor(slug, seed)) for slug in slugs]
    if locked:
        blocks = [(slug, noise(f"{seed}:{slug}:locked", len(block))) for slug, block in blocks]

    result = None
    try:
        if data.startswith(b"\xff\xd8\xff"):
            result = _jpeg(data, blocks, seed)
        elif data.startswith(PNG):
            result = _png(data, blocks, seed)
        elif data.startswith(b"%PDF"):
            result = _pdf(data, blocks, seed)
        elif data.startswith(b"PK\x03\x04"):
            result = _zip(data, blocks, seed)
        elif _registered(data) is not None:
            fmt = _registered(data)
            result = (_chunks if fmt.kind == "chunks" else _package)(data, blocks, seed, fmt)
        else:
            head = data[:256].decode("utf-8", "ignore").lstrip().lower()
            plain = b"\x00" not in data[:512]
            if plain and head.startswith(("<!--snp", "<!doctype", "<?xml", "<html", "<svg")):
                result = _markup(data, blocks, seed)
            elif plain:
                result = _text(data, blocks, seed)
    except (ValueError, struct.error, IndexError):
        result = None
    return result if result is not None else _anywhere(data, blocks, seed, real)
