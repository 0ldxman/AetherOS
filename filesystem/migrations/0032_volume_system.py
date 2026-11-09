from django.db import migrations, models


def mark_existing(apps, schema_editor):
    """Тома отличий, созданные до появления поля: метка «Отличия …», слаг «…-own» и локальное монтирование на одну машину целиком.
    Обычный том, который кто-то смонтировал на одну машину вручную, системным не становится."""
    Volume = apps.get_model("filesystem", "Volume")
    MachineMount = apps.get_model("machines", "MachineMount")
    for volume in Volume.objects.filter(label__startswith="Отличия ", slug__contains="-own"):
        mounts = list(MachineMount.objects.filter(volume=volume))
        if mounts and len({m.machine_id for m in mounts}) == 1 and all(m.mode == "local" and m.volume_path == "" for m in mounts):
            volume.system = True
            volume.save(update_fields=["system"])


class Migration(migrations.Migration):

    dependencies = [
        ("filesystem", "0031_volume_size"),
        ("machines", "0035_system_style"),
    ]

    operations = [
        migrations.AddField(
            model_name="volume",
            name="system",
            field=models.BooleanField(default=False, help_text="Создан автоматически для одной машины и хранит её отличия от общих томов. Остальные тома это обычные диски мира.", verbose_name="Системный"),
        ),
        migrations.RunPython(mark_existing, migrations.RunPython.noop),
    ]
