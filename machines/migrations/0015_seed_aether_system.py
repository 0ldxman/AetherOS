from django.db import migrations


def seed(apps, schema_editor):
    SystemType = apps.get_model("machines", "SystemType")
    SystemType.objects.get_or_create(code="AETHER", defaults={"name": "Aether", "path_style": "unix"})


class Migration(migrations.Migration):
    dependencies = [("machines", "0014_system_types_places_mounts")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
