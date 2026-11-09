import django.db.models.deletion
from django.db import migrations, models


def fill(apps, schema_editor):
    """Тома отличий, которые уже есть: метка «Отличия …», слаг «…-own», локально и целиком на «/» одной машины."""
    Volume = apps.get_model("filesystem", "Volume")
    MachineMount = apps.get_model("machines", "MachineMount")
    Machine = apps.get_model("machines", "Machine")
    taken = set()
    for volume in Volume.objects.filter(label__startswith="Отличия ", slug__contains="-own").order_by("slug"):
        mounts = list(MachineMount.objects.filter(volume=volume))
        machines = {m.machine_id for m in mounts}
        if len(machines) != 1 or not all(m.mode == "local" and m.volume_path == "" for m in mounts):
            continue
        if not any(m.mount_path == "/" for m in mounts):
            continue
        machine_id = next(iter(machines))
        if machine_id in taken:
            continue
        taken.add(machine_id)
        Machine.objects.filter(pk=machine_id, overlay__isnull=True).update(overlay=volume)


class Migration(migrations.Migration):

    dependencies = [
        ("machines", "0035_system_style"),
        ("filesystem", "0033_remove_volume_system"),
    ]

    operations = [
        migrations.AddField(
            model_name="machine",
            name="overlay",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="overlay_of", to="filesystem.volume",
                verbose_name="Том отличий",
                help_text="Единственный том с отличиями этой машины от общих дисков. Лежит над всеми её дисками, на любых точках монтирования; сюда ложатся правки общих файлов. Пусто: создастся сам при первой правке.",
            ),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
