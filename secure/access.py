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