"""Почтовые адреса и маски.

Адрес это имя@хост (will_smith@apollo.mail). Получатели письма это список адресов, где
«*» заменяет любые символы: *@aether-* подходит всем ящикам на aether-main и aether-null,
а просто * подходит всем. Регистр не важен.
"""
import re

from django.core.exceptions import ValidationError

SEPARATORS = re.compile(r"[\s,;]+")
ADDRESS = re.compile(r"^[^\s@*,;]+@[^\s@*,;]+$")
MASK = re.compile(r"^[^\s@,;]+@[^\s@,;]+$")


def split(text):
    """Адреса и маски из текста: по одному в строку, можно через запятую."""
    return [part for part in SEPARATORS.split(text or "") if part]


def validate_address(value):
    if not ADDRESS.match(value or ""):
        raise ValidationError("Нужен адрес вида имя@хост (без пробелов и «*»).")


def validate_masks(value):
    for part in split(value):
        if part != "*" and not MASK.match(part):
            raise ValidationError(f"«{part}»: нужен адрес вида имя@хост, где «*» заменяет любые символы.")


def _compile(mask):
    return re.compile("^" + ".*".join(re.escape(piece) for piece in mask.lower().split("*")) + "$", re.DOTALL)


def matches(mask, address):
    return _compile(mask).match((address or "").lower()) is not None


def matches_any(masks_text, address):
    return any(matches(mask, address) for mask in split(masks_text))


def same(first, second):
    return (first or "").lower() == (second or "").lower()
