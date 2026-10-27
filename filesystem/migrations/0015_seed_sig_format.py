"""Формат файла подписи (.sig): его опознают вьювер raw и ftyp по первой строке блока."""
from django.db import migrations

TEMPLATE = "-----BEGIN SIGNATURE-----\nKeyname: {ref}\n\n{body}\n-----END SIGNATURE-----\n"


def seed(apps, schema_editor):
    Format = apps.get_model("filesystem", "FileFormat")
    Format.objects.get_or_create(
        name="sig", defaults=dict(title="SIG detached signature", extension=".sig", kind="text", template=TEMPLATE)
    )


class Migration(migrations.Migration):

    dependencies = [
        ("filesystem", "0014_file_signature"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
