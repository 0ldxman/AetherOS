"""base64 стал кодировкой слоя binary (cvt enc base64): слой base64 и команда enc убраны, старые записи переписаны."""
import re

from django.db import migrations

OLD_LAYER = re.compile(r"(?m)^(\s*>\s*)base64\b")


def move(apps, schema_editor):
    Encoding = apps.get_model("filesystem", "FileEncoding")
    for name, title, param in (("base64", "Base64", ""), ("base64url", "Base64 (URL alphabet)", "url")):
        Encoding.objects.get_or_create(name=name, defaults=dict(title=title, kind="base64", param=param))

    File = apps.get_model("filesystem", "MachineFile")
    for item in File.objects.filter(state__contains="base64"):
        fixed = OLD_LAYER.sub(r"\1binary base64", item.state)
        if fixed != item.state:
            File.objects.filter(pk=item.pk).update(state=fixed)


class Migration(migrations.Migration):

    dependencies = [
        ("filesystem", "0017_encoding_base64"),
    ]

    operations = [
        migrations.RunPython(move, migrations.RunPython.noop),
    ]
