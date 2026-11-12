"""Элементы панели переехали из переключателей стола (SystemType.widgets, widget_places) в раскладку панели (style_parts["panel"])."""
from django.db import migrations

# раскладки видов на момент переноса (machines/world/panel.py, PRESETS)
PRESETS = {
    "aether": {"start": ["machine"], "center": ["clock"], "end": ["ping"]},
    "classic": {"start": ["launcher", "tasks"], "center": [], "end": ["ping", "clock"]},
    "modern": {"start": ["launcher", "tasks"], "center": [], "end": ["ping", "notices", "clock"]},
    "gnome": {"start": ["launcher"], "center": ["clock"], "end": ["ping", "machine"]},
    "workbench": {"start": ["clock", "workspaces", "apps", "actions"], "center": [], "end": ["ping"]},
    "tui": {"start": ["brand", "tasks"], "center": [], "end": ["ping", "clock"]},
    "phosphor": {"start": ["brand"], "center": [], "end": ["ping", "clock"]},
}
PANEL_KEYS = ("machine", "notices", "launcher", "search", "tasks", "workspaces", "console", "clock", "ping")
EXITS = ("launcher", "machine", "actions")


def forward(apps, schema_editor):
    SystemType = apps.get_model("machines", "SystemType")
    for system in SystemType.objects.all():
        widgets = dict(system.widgets or {})
        places = dict(system.widget_places or {})
        look = system.style if system.style in PRESETS else "aether"
        slots = {slot: list(keys) for slot, keys in PRESETS[look].items()}
        changed = False
        for key in PANEL_KEYS:
            value = widgets.pop(key, None)
            where = next((slot for slot in slots if key in slots[slot]), None)
            if value is False and where:
                slots[where].remove(key)
                changed = True
            elif value is True and not where:
                slot = places.get(key) or ("start" if key in ("machine", "launcher", "notices") else "end")
                slots[slot if slot in slots else "end"].append(key)
                changed = True
            places.pop(key, None)
        if look == "workbench" and widgets.get("dock") is False and "apps" in slots["start"]:
            slots["start"].remove("apps")              # раньше док Workbench жил в передней панели
            widgets.pop("dock")
            changed = True
        if changed and look not in ("tui", "phosphor") and not any(key in slots[slot] for slot in slots for key in EXITS):
            slots["start"].insert(0, "launcher")       # выход из сеанса остаётся
        parts = dict(system.style_parts or {})
        if changed:
            parts["panel"] = {**parts.get("panel", {}), **slots}
        if changed or widgets != (system.widgets or {}) or places != (system.widget_places or {}):
            system.widgets, system.widget_places, system.style_parts = widgets, places, parts
            system.save(update_fields=["widgets", "widget_places", "style_parts"])


class Migration(migrations.Migration):
    dependencies = [("machines", "0044_system_style_parts")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
