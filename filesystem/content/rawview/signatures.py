"""Подписи в байтах файла: блок в стиле PEM после содержимого.

    -----BEGIN SIGNATURE-----
    Keyname: director
    Date: 2026-10-26

    q3Fz8hT0... (подпись)
    -----END SIGNATURE-----

Подпись это HMAC от хеша содержимого, посчитанный секретом системы для этого ключа: поддельную подпись без ключа не
сделать, а любая правка содержимого (в том числе вырезка blk) её ломает. Блоки подряд лежат в конце файла, хеш считается
по всему, что идёт до первого блока. Отдельная подпись (.sig) это файл с таким же блоком, а хеш считается по другому файлу.
Слои работают поверх: под шифром подписей не видно. Если источник закрыт игроку, на месте блоков шум той же длины.
"""
import base64
import hashlib
import hmac
import re

from django.conf import settings

from filesystem.content.rawview.noise import noise

LABEL = "SIGNATURE"
BEGIN = f"-----BEGIN {LABEL}-----"
END = f"-----END {LABEL}-----"
BLOCK = re.compile(
    rf"{re.escape(BEGIN)}\r?\nKeyname: ([A-Za-z0-9_.:-]{{1,64}})\r?\n(?:Date: (\d{{4}}-\d{{2}}-\d{{2}})\r?\n)?\r?\n"
    rf"([A-Za-z0-9+/=\r\n]+?){re.escape(END)}"
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def mac(slug, hexhash):
    """Подпись ключа slug под хешем: считать её умеет только система (и команда ward sign от имени игрока с ключом)."""
    secret = f"signature:{settings.SECRET_KEY}".encode()
    return hmac.new(secret, f"{slug}:{hexhash}".encode(), hashlib.sha256).digest()


def block(slug, hexhash, seed="", date=None):
    """Блок подписи: шапка и 64 байта в base64 (первые 32 это подпись, дальше стабильный шум для вида)."""
    raw = mac(slug, hexhash) + noise(f"{seed}:{slug}:sig", 32)
    text = base64.b64encode(raw).decode()
    lines = "\n".join(text[i:i + 64] for i in range(0, len(text), 64))
    stamp = f"Date: {date}\n" if date else ""
    return f"{BEGIN}\nKeyname: {slug}\n{stamp}\n{lines}\n{END}\n".encode()


def embed(data, signatures, seed, locked=False):
    """data с блоками подписей в конце. signatures: [(слаг, дата или None, верна ли)]. locked: блоки заменены шумом."""
    if not signatures:
        return data
    real = digest(data)
    forged = digest(data + b"forged")
    blocks = [block(slug, real if valid else forged, seed, date) for slug, date, valid in signatures]
    if locked:
        blocks = [noise(f"{seed}:sig{i}:locked", len(item)) for i, item in enumerate(blocks)]
    return data + b"".join(blocks)


def find(data):
    """Блоки подписей в байтах: [{start, slug, date, mac}]."""
    found = []
    for match in BLOCK.finditer(data.decode("latin-1")):
        try:
            payload = base64.b64decode("".join(match.group(3).split()))
        except ValueError:
            continue
        found.append({"start": match.start(), "slug": match.group(1), "date": match.group(2), "mac": payload[:32]})
    return found


def check(item, content):
    """Сходится ли подпись item с содержимым content."""
    return hmac.compare_digest(item["mac"], mac(item["slug"], digest(content)))
