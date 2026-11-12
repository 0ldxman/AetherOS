"""Док стал дополнительной панелью: style_parts["dock"] делится на "panel2" (есть, край, форма, автоскрытие, кнопка «все приложения»)
и "apps" (размер значков, подписи, метка запущенных — параметры элемента «Быстрый запуск»)."""
from django.db import migrations


def forward(apps, schema_editor):
    SystemType = apps.get_model("machines", "SystemType")
    for system in SystemType.objects.all():
        parts = dict(system.style_parts or {})
        dock = parts.pop("dock", None)
        if dock is None:
            continue
        panel2 = {key: dock[key] for key in ("show", "edge", "form", "hide") if key in dock}
        quick = {key: dock[key] for key in ("size", "labels", "mark") if key in dock}
        if dock.get("grid") == "on":
            panel2.update({"start": ["apps"], "center": [], "end": ["allapps"]})
        elif dock.get("grid") == "off":
            panel2.update({"start": ["apps"], "center": [], "end": []})
        if panel2:
            parts["panel2"] = panel2
        if quick:
            parts["apps"] = quick
        system.style_parts = parts
        system.save(update_fields=["style_parts"])


class Migration(migrations.Migration):
    dependencies = [("machines", "0046_dock_parameters")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
