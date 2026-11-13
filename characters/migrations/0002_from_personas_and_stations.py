import re

from django.db import migrations


def _code(name, taken):
    clean = re.sub(r"[^A-Z0-9]", "", (name or "").upper()) or "CHR"
    digit = re.search(r"[0-9]", clean[2:])
    base = (clean[:2] + digit.group(0)) if digit else (clean + "XX")[:3]
    candidates = [base] + [base[:2] + str(n) for n in range(10)] + [base[0] + f"{n:02d}" for n in range(100)]
    return next(code for code in candidates if code not in taken)


def _color(name):
    total = 0
    for ch in name or "":
        total = (total * 31 + ord(ch)) % 2**32
    return total % 4


def forward(apps, schema_editor):
    """Персонажи из того, что уже было: каждый персонаж почты и каждая станция вида «персонаж» получают своё лицо."""
    Character = apps.get_model("characters", "Character")
    Persona = apps.get_model("mail", "Persona")
    Station = apps.get_model("air", "Station")
    taken = set(Character.objects.values_list("code", flat=True))
    for station in Station.objects.filter(kind="character", character__isnull=True):
        code = _code(station.name, taken)
        taken.add(code)
        made = Character.objects.create(code=code, name=station.label or station.name, callsign=station.name, color=_color(station.name))
        station.character = made
        station.save(update_fields=["character"])
    for persona in Persona.objects.filter(character__isnull=True):
        name = persona.name or persona.address.split("@")[0]
        code = _code(name, taken)
        taken.add(code)
        made = Character.objects.create(code=code, name=name, color=_color(name), note=persona.note)
        persona.character = made
        persona.save(update_fields=["character"])


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0001_initial"),
        ("mail", "0016_persona_character"),
        ("air", "0005_station_character"),
    ]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
