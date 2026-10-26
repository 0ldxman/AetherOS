"""Кодировки для слоя binary: настоящий текст внутри, но в виде, который нужно опознать и преобразовать обратно (cvt)."""
import base64
import codecs
import gzip

MORSE = {
    **dict(zip("abcdefghijklmnopqrstuvwxyz", ".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --..".split())),
    **dict(zip("0123456789", "----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----.".split())),
}


def _morse(data):
    words = data.decode("utf-8", "replace").lower().split(" ")
    return " / ".join(" ".join(MORSE[ch] for ch in word if ch in MORSE) for word in words).encode()


ENCODERS = {
    "utf16": lambda data: data.decode("utf-8", "replace").encode("utf-16-le"),
    "hex": lambda data: " ".join(f"{byte:02x}" for byte in data).encode(),
    "rot13": lambda data: codecs.encode(data.decode("utf-8", "replace"), "rot13").encode(),
    "gzip": lambda data: gzip.compress(data, mtime=0),
    "morse": _morse,
}


def encode(name, data):
    """Данные в кодировке name; незнакомая кодировка оставляет их как есть."""
    encoder = ENCODERS.get(name)
    return encoder(data) if encoder else data


def known(name):
    return name in ENCODERS


def wrap_base64(data):
    """Как утилита base64: строки по 76 символов."""
    text = base64.b64encode(data).decode()
    return "\n".join(text[i:i + 76] for i in range(0, len(text), 76)).encode() + b"\n"
