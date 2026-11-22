from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import time_parts

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if time_parts(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0024_journal_and_panel")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
