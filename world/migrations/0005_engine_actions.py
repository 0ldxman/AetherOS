"""Действия триггеров в словаре движка (engine/actions.py): у мира свои имена world_flag, world_unflag, world_count, letter_all."""
from django.db import migrations

RENAME = {"flag": "world_flag", "unflag": "world_unflag", "count": "world_count", "letter": "letter_all"}


def convert(actions):
    return [{**action, "do": RENAME.get(action.get("do"), action.get("do"))} if isinstance(action, dict) else action for action in actions or []]


def forward(apps, schema_editor):
    for trigger in apps.get_model("world", "WorldTrigger").objects.all():
        new = convert(trigger.actions)
        if new != trigger.actions:
            trigger.actions = new
            trigger.save(update_fields=["actions"])


class Migration(migrations.Migration):
    dependencies = [("world", "0004_letter_condition")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
