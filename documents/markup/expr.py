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
_SLUG = re.compile(r"[A-Za-z0-9_-]+|world:[a-z0-9][a-z0-9_-]{0,63}(?:(?:>=|<=|>|<|=)-?\d+)?|flag:[A-Za-z0-9_-]{1,64}")   # ключ, метка/счётчик мира, метка игрока


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


def format_expr(node):
    """Условие в формате secure/access.py (то, что отдаёт parse_expr) -> текст. Пустая группа и пустой ключ пропускаются,
    пустое условие даёт "". Скобки ставятся только там, где без них смысл изменился бы: группа в группе, группа под not."""

    if isinstance(node, str):
        return node.strip()

    if not isinstance(node, dict) or len(node) != 1:
        raise SpoilerSyntaxError("Условие собрано неверно.")

    (kind, inner), = node.items()

    if kind == "not":
        text = format_expr(inner)
        return "" if not text else f"not ({text})" if _is_group(inner) else f"not {text}"

    if kind not in ("all", "any") or not isinstance(inner, list):
        raise SpoilerSyntaxError("Условие собрано неверно.")

    word = " and " if kind == "all" else " or "
    parts = []

    for part in inner:
        text = format_expr(part)

        if text:
            # and внутри or скобок не требует (он связывает сильнее); остальные группы в группе берутся в скобки
            nested = _is_group(part) and len(_flat(part)) > 1
            wrap = nested and not (kind == "any" and _kind(part) == "all")
            parts.append(f"({text})" if wrap else text)

    return word.join(parts)


def _kind(node):
    return next(iter(node)) if isinstance(node, dict) else ""


def _is_group(node):
    return _kind(node) in ("all", "any")


def _flat(node):
    """Непустые части группы (для решения о скобках)."""
    return [part for part in node[_kind(node)] if format_expr(part)]
