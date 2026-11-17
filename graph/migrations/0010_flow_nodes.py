from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import flow_nodes

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if flow_nodes(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0009_events")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
