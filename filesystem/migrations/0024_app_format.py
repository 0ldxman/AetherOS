"""Формат файла приложения (.app): текст из строк «ключ значение», см. filesystem/appfile.py."""
from django.db import migrations


def seed(apps, schema_editor):
    Format = apps.get_model("filesystem", "FileFormat")
    Format.objects.get_or_create(
        name="app",
        defaults=dict(title="APP application", extension=".app", kind="text", template="{body}", content="text", editable=True),
    )


class Migration(migrations.Migration):
    dependencies = [("filesystem", "0023_item_history")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
