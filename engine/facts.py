"""Факты игрока для условий. Условие (secure/access.py) проверяется по набору строк: слаги ключей, flag:<имя> — личные метки
игрока, а world:… читается из мира отдельно. Набор собирается здесь, чтобы любое место с условием видело одно и то же."""
FLAG = "flag:"
WORLD = "world:"
PREFIXES = (FLAG, WORLD)


def flags(user):
    """Личные метки игрока (ставятся действиями flag/unflag)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    from mail.models import Flag

    return set(Flag.objects.filter(user=user).values_list("name", flat=True))


def of(user, keys=()):
    """Ключи игрока плюс его метки строками flag:<имя>."""
    return frozenset(keys) | {FLAG + name for name in flags(user)}


def is_key(text):
    """Строка условия — это ключ, а не метка игрока или мира."""
    return isinstance(text, str) and not text.startswith(PREFIXES)
