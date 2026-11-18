from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import join_nodes

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if join_nodes(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0016_wait_condition")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
