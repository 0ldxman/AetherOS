from django.core.exceptions import ValidationError


def satisfied(req, keys):
    """Проверяет условие из поля requirements.

    req  - условие: пустое (открыто всем), строка-slug ключа
           или словарь {"all": [...]}, {"any": [...]}, {"not": ...}
    keys - набор slug'ов ключей, которые сейчас доступны игроку
    """
    if not req:
        return True
    if isinstance(req, str):
        return req in keys
    if "all" in req:
        return all(satisfied(r, keys) for r in req["all"])
    if "any" in req:
        return any(satisfied(r, keys) for r in req["any"])
    if "not" in req:
        return not satisfied(req["not"], keys)
    return False  # неизвестное условие: закрываем доступ, а не открываем


def _check(req):
    """Строгая проверка формы условия."""

    if isinstance(req, dict) and not req:
        return

    if isinstance(req, str) and req:
        return

    if isinstance(req, dict) and len(req) == 1:
        (op, val), = req.items()

        if op in ("all", "any") and isinstance(val, list) and val:
            for r in val:
                _check(r)
            return

        if op == "not" and val:
            _check(val)
            return

    raise ValidationError(
        f"Неверное условие: {req!r}"
    )


def validate_requirements(req):
    """Валидатор для поля requirements: пустое значение допустимо (открыто всем)."""
    if not req:
        return
    _check(req)

def format_condition(req):
    """Условие из поля requirements -> читаемая строка: key_a and (key_b or not key_c).

    Обратное к wiki.markup.parse_expr; пустое условие даёт пустую строку.
    """
    return _format(req, 0)


def _format(req, parent):
    # приоритет: or (1) < and (2) < not (3); скобки нужны, если внутри слабее, чем снаружи
    if not req:
        return ""
    if isinstance(req, str):
        return req
    if "not" in req:
        return "not " + _format(req["not"], 3)
    op, level = ("and", 2) if "all" in req else ("or", 1)
    parts = req.get("all") or req.get("any") or []
    text = f" {op} ".join(_format(p, level) for p in parts)
    return f"({text})" if len(parts) > 1 and level < parent else text


def condition_slugs(req):
    """Все slug'и ключей в условии (в порядке появления, с повторами)."""
    if not req:
        return []
    if isinstance(req, str):
        return [req]
    found = []
    for value in req.values():
        for part in value if isinstance(value, list) else [value]:
            found.extend(condition_slugs(part))
    return found
