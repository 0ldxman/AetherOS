"""Файлы приложений называют иконку из каталога (icon), а не текстовый значок (glyph)."""
from django.db import migrations

ICON_OF_GLYPH = {">_": "terminal", "@": "mail", "W": "book", "M": "map", "S": "settings", "✉": "mail", "◎": "map"}


def forward(apps, schema_editor):
    Item = apps.get_model("filesystem", "Item")
    for item in Item.objects.filter(format="app"):
        lines, changed = [], False
        for line in item.body.splitlines():
            key, _, value = line.strip().partition(" ")
            if key.lower() == "glyph":
                lines.append(f"icon {ICON_OF_GLYPH.get(value.strip(), 'app')}")
                changed = True
            else:
                lines.append(line)
        if changed:
            item.body = "\n".join(lines) + "\n"
            item.save(update_fields=["body"])


class Migration(migrations.Migration):

    dependencies = [("filesystem", "0036_item_asset_removed")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
