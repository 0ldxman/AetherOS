"""Кодировки слоя binary: настоящий текст внутри, но в виде, который нужно опознать и вернуть командой cvt.

Какие кодировки есть, решает реестр (FileEncoding в админке); здесь только виды: codec, hex, rot, xor, gzip, morse, rot47, bin, dec, oct, url, base85, uu, atbash...
"""
import base64
import binascii
import codecs
import gzip
import string
from urllib.parse import quote_from_bytes

from filesystem.rawview import registry

MORSE = {
    **dict(zip("abcdefghijklmnopqrstuvwxyz", ".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --..".split())),
    **dict(zip("0123456789", "----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----.".split())),
}


def _morse(data, param):
    words = data.decode("utf-8", "replace").lower().split(" ")
    return " / ".join(" ".join(MORSE[ch] for ch in word if ch in MORSE) for word in words).encode()


def _rot(data, param):
    shift = int(param or 13) % 26
    table = {}
    for alphabet in (string.ascii_lowercase, string.ascii_uppercase):
        table.update({ord(ch): alphabet[(i + shift) % 26] for i, ch in enumerate(alphabet)})
    return data.decode("utf-8", "replace").translate(table).encode()


def _rot47(data, param):
    table = {code: 33 + (code - 33 + 47) % 94 for code in range(33, 127)}
    return data.decode("utf-8", "replace").translate(table).encode()


def _atbash(data, param):
    table = {}
    for alphabet in (string.ascii_lowercase, string.ascii_uppercase):
        table.update({ord(ch): alphabet[25 - i] for i, ch in enumerate(alphabet)})
    return data.decode("utf-8", "replace").translate(table).encode()


def _uu(data, param):
    lines = [binascii.b2a_uu(data[i:i + 45]).decode().rstrip("\n") for i in range(0, len(data), 45)]
    return ("begin 644 data\n" + "\n".join(lines) + "\n`\nend\n").encode()


def _byte(param):
    return int(str(param or "0"), 0) & 0xFF


ENCODERS = {
    "codec": lambda data, param: data.decode("utf-8", "replace").encode(param or "utf-16-le", "replace"),
    "hex": lambda data, param: (param if param != "" else " ").join(f"{byte:02x}" for byte in data).encode(),
    "rot": _rot,
    "xor": lambda data, param: bytes(byte ^ _byte(param) for byte in data),
    "gzip": lambda data, param: gzip.compress(data, mtime=0),
    "morse": _morse,
    "reverse": lambda data, param: data[::-1],
    "base32": lambda data, param: base64.b32encode(data),
    "rot47": _rot47,
    "bin": lambda data, param: " ".join(f"{byte:08b}" for byte in data).encode(),
    "dec": lambda data, param: " ".join(str(byte) for byte in data).encode(),
    "oct": lambda data, param: " ".join(f"{byte:03o}" for byte in data).encode(),
    "url": lambda data, param: quote_from_bytes(data, safe="").encode(),
    "base85": lambda data, param: base64.b85encode(data),
    "uu": _uu,
    "atbash": _atbash,
}


def known(name):
    return registry.encoding_named(name) is not None


def encode(name, data):
    """Данные в кодировке name; незнакомая кодировка оставляет их как есть."""
    found = registry.encoding_named(name)
    if found is None or found.kind not in ENCODERS:
        return data
    return ENCODERS[found.kind](data, found.param)


def valid_param(kind, param):
    """Текст ошибки или None: подходит ли параметр кодировки этого вида."""
    if kind == "codec":
        try:
            codecs.lookup(param or "utf-16-le")
        except LookupError:
            return f"нет такого кодека: {param}"
    if kind in ("rot", "xor") and param:
        try:
            int(str(param), 0)
        except ValueError:
            return "параметр должен быть числом"
    return None


def wrap_base64(data):
    """Как утилита base64: строки по 76 символов."""
    text = base64.b64encode(data).decode()
    return "\n".join(text[i:i + 76] for i in range(0, len(text), 76)).encode() + b"\n"
