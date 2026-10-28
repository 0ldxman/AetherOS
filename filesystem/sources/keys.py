"""Ключи и подписи: файлы, чьё содержимое задаёт сам адрес, а не запись в базе."""
from django.urls import reverse
from django.utils.http import urlencode

from filesystem.sources.base import Content, Payload, Source

KEY_PREFIX = "keys/"
SIGNATURE_PREFIX = "sig/"


def key_address(slug):
    return KEY_PREFIX + slug


def signature_address(slug, hexhash):
    return f"{SIGNATURE_PREFIX}{slug}/{hexhash}"


def text_window(path):
    """Ключ и подпись показываются текстом: их содержимое то же, что в raw, но в простом окне."""
    return Content(url=reverse("fsview:text") + "?" + urlencode({"path": path}))


class KeySource(Source):
    """Файл ключа в папке секретов игрока: блок ключа, как он лежит в байтах файлов."""

    name = "key"

    def accepts(self, address):
        return address.parts[:1] == ["keys"] and len(address.parts) == 2

    def payload(self, machine_file, address, keys, reader, viewer):
        from filesystem.rawview import keys as blocks

        slug = address.parts[1]
        return Payload(kind="key", layout="raw", body=blocks.armor(slug, f"store:{slug}"), stamp=f"key:{slug}")

    def shows(self, url):
        return url.strip().startswith(KEY_PREFIX)

    def window(self, url, path):
        return text_window(path)


class SignatureSource(Source):
    """Файл подписи (ward sign): блок подписи ключа под хешем другого файла."""

    name = "signature"

    def accepts(self, address):
        return address.parts[:1] == ["sig"] and len(address.parts) == 3

    def payload(self, machine_file, address, keys, reader, viewer):
        from filesystem.rawview import signatures

        slug, hexhash = address.parts[1], address.parts[2]
        return Payload(kind="signature", layout="raw", body=signatures.block(slug, hexhash, f"sig:{slug}"), stamp=f"sig:{slug}:{hexhash}")

    def shows(self, url):
        return url.strip().startswith(SIGNATURE_PREFIX)

    def window(self, url, path):
        return text_window(path)
