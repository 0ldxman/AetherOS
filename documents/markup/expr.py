"""Условия спойлера: разбор выражения key_a and (key_b or not key_c).

Часть пакета documents.markup (описание синтаксиса: documents/markup/__init__.py).
"""

import re

from documents.markup.constants import EXPR_MAX_LEN


# =========================================================
# Условие спойлера
# =========================================================

class SpoilerSyntaxError(ValueError):
    pass


_KEYWORDS = {"and", "or", "not"}
_SLUG = re.compile(r"[A-Za-z0-9_-]+")


def parse_expr(src):
    """Условие спойлера -> условие в формате secure/access.py."""

    src = (src or "").strip()

    if not src:
        raise SpoilerSyntaxError("Пустое условие.")

    if len(src) > EXPR_MAX_LEN:
        raise SpoilerSyntaxError("Слишком длинное условие.")

    words = (
        src
        .replace("(", " ( ")
        .replace(")", " ) ")
        .split()
    )

    pos = 0

    def peek():
        return words[pos] if pos < len(words) else None

    def take():
        nonlocal pos
        word = peek()
        pos += 1
        return word

    def parse_or():
        parts = [parse_and()]

        while peek() == "or":
            take()
            parts.append(parse_and())

        return (
            parts[0]
            if len(parts) == 1
            else {"any": parts}
        )

    def parse_and():
        parts = [parse_not()]

        while peek() == "and":
            take()
            parts.append(parse_not())

        return (
            parts[0]
            if len(parts) == 1
            else {"all": parts}
        )

    def parse_not():
        if peek() == "not":
            take()
            return {"not": parse_not()}

        return parse_atom()

    def parse_atom():
        word = take()

        if word is None:
            raise SpoilerSyntaxError("Условие оборвано.")

        if word == "(":
            inner = parse_or()

            if take() != ")":
                raise SpoilerSyntaxError(
                    "Нет закрывающей скобки."
                )

            return inner

        if (
            word in _KEYWORDS
            or word == ")"
            or not _SLUG.fullmatch(word)
        ):
            raise SpoilerSyntaxError(
                f"Неожиданное слово: {word!r}."
            )

        return word

    result = parse_or()

    if pos != len(words):
        raise SpoilerSyntaxError(
            f"Лишнее слово: {words[pos]!r}."
        )

    return result
