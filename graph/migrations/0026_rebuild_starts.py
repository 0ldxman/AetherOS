"""Старты всех сценариев заново: апгрейды документа (0009 и другие) меняли ноды, но старты не пересобирали —
новая нода-триггер не слушала события, пока граф не пересохранят в Студии."""
from django.db import migrations


def forward(apps, schema_editor):
    Graph = apps.get_model("graph", "Graph")
    if not Graph.objects.exists():
        return
    from graph import runtime
    from graph.models import Graph as Live

    for graph in Live.objects.all():
        try:
            runtime.rebuild_starts(graph)
        except Exception:                                   # noqa: BLE001 — сломанный граф не мешает миграции, его старты пересоберёт сохранение
            pass


class Migration(migrations.Migration):
    dependencies = [("graph", "0025_time_parts")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop, elidable=True)]
