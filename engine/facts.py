"""Факты игрока для условий. Условие (secure/access.py) проверяется по набору строк: слаги ключей игрока, его теги строками
tag:<имя>, его счётчики count:<имя>=<значение> и метка @user:<номер> (кто игрок — для значений «для игрока»).

Ключи условий на теги и счётчики (engine/values.py):
    tag:имя                              тег игрока
    tag:world:имя                        тег мира (короче: world:имя)
    tag:владелец:вещь:имя                общий тег вещи (character, machine, server, object, player)
    tag:владелец:вещь:имя@player         тег вещи для этого игрока
    count:…[оп число]                    то же для счётчиков; оп: >=, >, <=, <, =; без него — «больше нуля»
"""
import re

TAG = "tag:"
WORLD = "world:"
COUNT = "count:"
USER = "@user:"
PLAYER = "@player"
PREFIXES = (TAG, WORLD, COUNT, USER)
ATOM = re.compile(r"(tag|count):([^\s<>=]+?)(?:(>=|<=|>|<|=)(-?\d+))?")


def flags(user):
    """Теги игрока (имена)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    from engine import values

    return values.names(values.TAG, values.PLAYER, user.pk)


def counts(user):
    """Счётчики игрока строками count:<имя>=<значение> (условие count:имя>=N сравнивает с ними)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    from engine import values

    found = values._cached(values.PLAYER, user.pk, None)
    return {f"{COUNT}{name}={value}" for (kind, name), value in found.items() if kind == values.COUNT}


def of(user, keys=()):
    """Ключи игрока плюс его теги tag:<имя>, счётчики count:<имя>=<значение> и метка игрока @user:<номер>."""
    found = frozenset(keys) | {TAG + name for name in flags(user)} | counts(user)
    if user is not None and getattr(user, "is_authenticated", False):
        found |= {f"{USER}{user.pk}"}
    return found


def parse(text):
    """(вид tag|count, владелец, вещь, имя, для игрока, оператор, число) или None, если строка не ключ тега или счётчика."""
    match = ATOM.fullmatch(str(text or "").strip())
    if not match:
        return None
    kind, rest, op, number = match.groups()
    parts = rest.split(":")
    per = parts[-1].endswith(PLAYER)
    if per:
        parts[-1] = parts[-1][:-len(PLAYER)]
    if len(parts) == 1:
        owner, thing = "player", ""
    elif len(parts) == 2 and parts[0] == "world":
        owner, thing = "world", ""
    elif len(parts) == 3:
        owner, thing = parts[0], parts[1]
    else:
        return None
    from engine import values

    if owner not in values.OWNERS or not parts[-1] or (kind == "tag" and op):
        return None
    return kind, owner, thing, parts[-1].lower(), per, op, int(number) if number is not None else None


def _player_of(keys):
    pk = next((k[len(USER):] for k in keys if isinstance(k, str) and k.startswith(USER)), None)
    return int(pk) if pk and pk.isdigit() else None


def compare(text, keys):
    """Верен ли ключ тега или счётчика для игрока с фактами keys. Непонятная строка закрывает."""
    found = parse(text)
    if found is None:
        return False
    kind, owner, thing, name, per, op, number = found
    from engine import values

    if owner == "player" and not thing:             # своё: теги и счётчики уже в фактах (так работает и песочница почты)
        if kind == "tag":
            return f"{TAG}{name}" in keys
        value = next((int(k.split("=", 1)[1]) for k in keys if isinstance(k, str) and k.startswith(f"{COUNT}{name}=")), 0)
    else:
        oid = values.owner_id(owner, thing) if owner != "world" else 0
        user = _player_of(keys) if per else None
        if per and user is None:
            return False
        value = values.get(values.TAG if kind == "tag" else values.COUNT, owner, oid, name, user)
    if kind == "tag":
        return bool(value)
    if op is None:
        return value > 0
    return {">=": value >= number, "<=": value <= number, ">": value > number, "<": value < number, "=": value == number}[op]


def is_key(text):
    """Строка условия — это ключ, а не тег, счётчик или метка мира."""
    return isinstance(text, str) and not text.startswith(PREFIXES)
