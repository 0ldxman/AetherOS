"""Действия реплик кукловода в словаре движка: действия мира под именами world_flag, world_unflag, world_count."""
from django.db import migrations

RENAME = {"flag": "world_flag", "unflag": "world_unflag", "count": "world_count", "letter": "letter_all"}


def convert(actions):
    return [{**action, "do": RENAME.get(action.get("do"), action.get("do"))} if isinstance(action, dict) else action for action in actions or []]


def forward(apps, schema_editor):
    for reply in apps.get_model("characters", "Reply").objects.exclude(actions=[]):
        new = convert(reply.actions)
        if new != reply.actions:
            reply.actions = new
            reply.save(update_fields=["actions"])


class Migration(migrations.Migration):
    dependencies = [("characters", "0004_replies")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
