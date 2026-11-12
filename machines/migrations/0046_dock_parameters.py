"""Док переехал из переключателей стола (SystemType.widgets["dock"], widget_places["dock"]) в параметры (style_parts["dock"])."""
from django.db import migrations


def forward(apps, schema_editor):
    SystemType = apps.get_model("machines", "SystemType")
    for system in SystemType.objects.all():
        widgets = dict(system.widgets or {})
        places = dict(system.widget_places or {})
        if "dock" not in widgets and "dock" not in places:
            continue
        dock = {}
        if "dock" in widgets:
            dock["show"] = "on" if widgets.pop("dock") else "off"
        if places.get("dock") in ("bottom", "left", "right"):
            dock["edge"] = places["dock"]
        places.pop("dock", None)
        parts = dict(system.style_parts or {})
        if dock:
            parts["dock"] = {**parts.get("dock", {}), **dock}
        system.widgets, system.widget_places, system.style_parts = widgets, places, parts
        system.save(update_fields=["widgets", "widget_places", "style_parts"])


class Migration(migrations.Migration):
    dependencies = [("machines", "0045_panel_from_widgets")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
