"""Персонажи: код из имени, проверка, связь с каналами (почта, эфир)."""
import re

from django.core.exceptions import ValidationError

from characters.models import Character

COLORS = 4


def code_for(name, taken=()):
    """Свободный код из трёх знаков для имени: буквы и первая цифра (OPERATOR-7 → OP7), иначе три буквы (MAPT → MAP), при совпадении цифра в конце."""
    clean = re.sub(r"[^A-Z0-9]", "", (name or "").upper()) or "CHR"
    digit = re.search(r"[0-9]", clean[2:])
    base = (clean[:2] + digit.group(0)) if digit else (clean + "XX")[:3]
    taken = set(taken) | set(Character.objects.values_list("code", flat=True))
    if base not in taken:
        return base
    for n in range(10):
        found = base[:2] + str(n)
        if found not in taken:
            return found
    for n in range(100):
        found = base[0] + f"{n:02d}"
        if found not in taken:
            return found
    raise ValidationError("Нет свободного кода.")


def color_for(name):
    """Цвет кода по умолчанию: тот же, что раньше считал форум по имени."""
    total = 0
    for ch in name or "":
        total = (total * 31 + ord(ch)) % 2**32
    return total % COLORS


def channels(character):
    """Каналы персонажа: почтовые адреса и позывные станций."""
    return {
        "mail": list(character.personas.values_list("address", flat=True)),
        "air": list(character.stations.values_list("name", flat=True)),
    }
