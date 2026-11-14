"""Факты игрока для условий. Условие (secure/access.py) проверяется по набору строк: слаги ключей, flag:<имя> — личные метки
игрока, а world:… читается из мира отдельно. Набор собирается здесь, чтобы любое место с условием видело одно и то же."""
FLAG = "flag:"
WORLD = "world:"
COUNT = "count:"
CHAR = "char:"
PREFIXES = (FLAG, WORLD, COUNT, CHAR)


def flags(user):
    """Личные метки игрока (ставятся действиями flag/unflag)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    from mail.models import Flag

    return set(Flag.objects.filter(user=user).values_list("name", flat=True))


def counts(user):
    """Счётчики игрока строками count:<имя>=<значение> (условие count:имя>=N сравнивает с ними)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    from engine.models import PlayerValue

    return {f"{COUNT}{name}={value}" for name, value in PlayerValue.objects.filter(user=user).values_list("name", "value")}


def of(user, keys=()):
    """Ключи игрока плюс его метки строками flag:<имя> и счётчики count:<имя>=<значение>."""
    return frozenset(keys) | {FLAG + name for name in flags(user)} | counts(user)


def compare(text, keys):
    """count:имя[оп число] по фактам игрока; char:КОД:тег по персонажу. Без оператора count:имя — «больше нуля»."""
    import re

    if text.startswith(CHAR):
        _, code, tag = (text.split(":", 2) + ["", ""])[:3]
        from characters.models import Character

        found = Character.objects.filter(code=code.upper()).values_list("tags", flat=True).first()
        return tag.lower() in (found or [])
    match = re.fullmatch(r"count:([A-Za-z0-9_-]{1,64})(?:(>=|<=|>|<|=)(-?\d+))?", text)
    if not match:
        return False
    name, op, number = match.group(1), match.group(2), match.group(3)
    value = next((int(k.split("=", 1)[1]) for k in keys if isinstance(k, str) and k.startswith(f"{COUNT}{name}=")), 0)
    if op is None:
        return value > 0
    limit = int(number)
    return {">=": value >= limit, "<=": value <= limit, ">": value > limit, "<": value < limit, "=": value == limit}[op]


def is_key(text):
    """Строка условия — это ключ, а не метка игрока или мира."""
    return isinstance(text, str) and not text.startswith(PREFIXES)
