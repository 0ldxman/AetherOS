"""Исходы ответчиков в словаре движка: хук (текст alert/open/kick) разбирается на отдельные действия."""
from django.db import migrations

def split_hook(text):
    """Строки хука (alert … / open … / kick) — отдельные действия движка."""
    out = []
    for line in (text or "").splitlines():
        name, _, rest = line.strip().partition(" ")
        rest = rest.strip()
        if name == "kick":
            out.append({"do": "kick"})
        elif name == "open" and rest:
            out.append({"do": "open", "url": rest[1:-1] if len(rest) >= 2 and rest[0] == rest[-1] == "\"" else rest})
        elif name == "alert" and rest:
            words = rest.split()
            row = {"do": "alert", "message": words[0]}
            for word in words[1:]:
                key, _, value = word.partition("=")
                if key in ("count", "gap") and value.isdigit():
                    row[key] = int(value)
            out.append(row)
    return out


def convert(actions):
    out = []
    for action in actions or []:
        if isinstance(action, dict) and action.get("do") == "hook":
            out += split_hook(action.get("text", ""))
        else:
            out.append(action)
    return out


def forward(apps, schema_editor):
    for responder in apps.get_model("air", "Responder").objects.all():
        new = convert(responder.actions)
        if new != responder.actions:
            responder.actions = new
            responder.save(update_fields=["actions"])


class Migration(migrations.Migration):
    dependencies = [("air", "0005_station_character")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
