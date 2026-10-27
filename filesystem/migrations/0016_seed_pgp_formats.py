"""Заголовки зашифрованных файлов (OpenPGP-пакеты): по ним ftyp и вьювер узнают «PGP-файл»."""
from django.db import migrations

FORMATS = (
    ("pgps", "PGP symmetric key encrypted data", "8c 0d 04 09 03 08"),
    ("pgpk", "PGP public-key encrypted data", "85 01 0c 03"),
)


def seed(apps, schema_editor):
    Format = apps.get_model("filesystem", "FileFormat")
    for name, title, magic in FORMATS:
        Format.objects.get_or_create(name=name, defaults=dict(title=title, extension="", kind="signature", magic=magic))


class Migration(migrations.Migration):

    dependencies = [
        ("filesystem", "0015_seed_sig_format"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
