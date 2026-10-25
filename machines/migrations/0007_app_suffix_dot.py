from django.db import migrations, models


def add_dots(apps, schema_editor):
    App = apps.get_model("machines", "MachineApp")
    for app in App.objects.exclude(suffix=""):
        fixed = "." + app.suffix.strip().lstrip(".")
        if fixed != app.suffix:
            app.suffix = fixed
            app.save(update_fields=["suffix"])


class Migration(migrations.Migration):

    dependencies = [
        ("machines", "0006_profile_mail"),
    ]

    operations = [
        migrations.AlterField(
            model_name="machineapp",
            name="suffix",
            field=models.CharField(blank=True, help_text="Расширение после названия: db или .db (точка добавится сама). Можно не указывать.", max_length=16),
        ),
        migrations.RunPython(add_dots, migrations.RunPython.noop),
    ]
