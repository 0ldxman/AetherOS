"""Перенос меток и счётчиков в одно хранилище: метки и счётчики игрока, метки и счётчики мира (подписи — в описание), теги персонажей."""
from django.db import migrations


def move(apps, schema_editor):
    Value = apps.get_model("engine", "Value")
    ValueInfo = apps.get_model("engine", "ValueInfo")
    rows = []
    for flag in apps.get_model("mail", "Flag").objects.all():
        rows.append(Value(kind="tag", owner="player", owner_id=flag.user_id, name=flag.name.strip().lower()[:64], value=1, changed_at=flag.set_at))
    for row in apps.get_model("engine", "PlayerValue").objects.all():
        rows.append(Value(kind="count", owner="player", owner_id=row.user_id, name=row.name.lower(), value=row.value))
    for flag in apps.get_model("world", "WorldFlag").objects.all():
        rows.append(Value(kind="tag", owner="world", owner_id=0, name=flag.name, value=int(flag.on), changed_at=flag.changed_at, changed_by=flag.changed_by))
        if flag.label:
            ValueInfo.objects.create(kind="tag", owner="world", owner_id=0, name=flag.name, label=flag.label)
    for counter in apps.get_model("world", "WorldCounter").objects.all():
        rows.append(Value(kind="count", owner="world", owner_id=0, name=counter.name, value=counter.value, changed_at=counter.changed_at))
        if counter.label or counter.labels:
            ValueInfo.objects.create(kind="count", owner="world", owner_id=0, name=counter.name, label=counter.label, labels=counter.labels or {})
    for character in apps.get_model("characters", "Character").objects.all():
        for tag in dict.fromkeys(str(t).strip().lower() for t in character.tags or [] if str(t).strip()):
            rows.append(Value(kind="tag", owner="character", owner_id=character.pk, name=tag[:64], value=1))
    seen = set()
    unique = []
    for row in rows:
        key = (row.kind, row.owner, row.owner_id, row.name)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    Value.objects.bulk_create(unique)


class Migration(migrations.Migration):

    dependencies = [
        ("engine", "0005_values"),
        ("mail", "0017_engine_actions"),
        ("world", "0005_engine_actions"),
        ("characters", "0006_character_tags"),
    ]

    operations = [migrations.RunPython(move, migrations.RunPython.noop)]
