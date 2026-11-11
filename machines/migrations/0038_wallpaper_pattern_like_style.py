from django.db import migrations


def like_style(apps, schema_editor):
    """Прежние умолчания узора (шаг 24, белый, 15%) становятся «как в стиле»: сетка стиля и узор совпадают без подгонки."""
    SystemType = apps.get_model("machines", "SystemType")
    for system in SystemType.objects.exclude(wallpaper={}):
        data = system.wallpaper
        if data.get("pattern_size") == 24 and data.get("pattern_color") == "#ffffff" and data.get("pattern_opacity") == 15:
            system.wallpaper = {**data, "pattern_size": 0, "pattern_color": "", "pattern_opacity": 100}
            system.save(update_fields=["wallpaper"])


class Migration(migrations.Migration):
    dependencies = [("machines", "0037_system_wallpaper")]
    operations = [migrations.RunPython(like_style, migrations.RunPython.noop)]
