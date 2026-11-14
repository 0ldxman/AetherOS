"""Ключи условий: flag:имя → tag:имя, char:КОД:тег → tag:character:КОД:тег (в сохранённых условиях и сценариях)."""
import re

from django.db import migrations

FIELDS = {"condition", "read_if", "write_if", "create_if", "access", "key_condition"}
GRAPH_FIELDS = {"condition", "expr", "rows"}


def _text(value):
    value = re.sub(r"(?<![\w:])flag:", "tag:", value)
    return re.sub(r"(?<![\w:])char:([A-Za-z0-9]+):", r"tag:character:\1:", value)


def fix(value):
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        return [fix(v) for v in value]
    if isinstance(value, dict):
        return {k: fix(v) for k, v in value.items()}
    return value


def _nodes(doc):
    yield from (doc or {}).get("nodes") or []
    for group in ((doc or {}).get("groups") or {}).values():
        yield from (group or {}).get("nodes") or []


def rewrite(apps, schema_editor):
    for model in apps.get_models():
        names = [f.name for f in model._meta.concrete_fields if f.get_internal_type() == "JSONField" and f.name in FIELDS]
        for name in names:
            for row in model.objects.exclude(**{f"{name}__isnull": True}).only("pk", name):
                old = getattr(row, name)
                new = fix(old)
                if new != old:
                    model.objects.filter(pk=row.pk).update(**{name: new})
    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        changed = False
        for node in _nodes(graph.doc):
            data = node.get("data") if isinstance(node, dict) else None
            for key in GRAPH_FIELDS & set(data or {}):
                new = fix(data[key])
                if new != data[key]:
                    data[key], changed = new, True
        if changed:
            Graph.objects.filter(pk=graph.pk).update(doc=graph.doc)


class Migration(migrations.Migration):

    dependencies = [
        ("engine", "0008_condition_help"),
        ("mail", "0018_drop_flag"),
        ("world", "0006_drop_flags_counters"),
        ("air", "0006_engine_actions"),
        ("forum", "0007_rotation"),
        ("filesystem", "0039_format_content_without_message"),
        ("map", "0009_material_show_info"),
        ("machines", "0049_alter_loginevent_kind"),
        ("graph", "0002_wait_data"),
    ]

    operations = [migrations.RunPython(rewrite, migrations.RunPython.noop)]
