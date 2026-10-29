"""Формат файла журнала (.log): его текст строится из событий входа на машине, см. filesystem/content/sources/log.py."""
from django.db import migrations


def seed(apps, schema_editor):
    Format = apps.get_model("filesystem", "FileFormat")
    Format.objects.get_or_create(
        name="log", defaults=dict(title="LOG authentication log", extension=".log", kind="text", template="{body}", content="none"),
    )


class Migration(migrations.Migration):
    dependencies = [("filesystem", "0026_rights_and_groups")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
