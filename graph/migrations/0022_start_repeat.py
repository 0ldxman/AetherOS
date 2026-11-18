from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import start_repeat

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if start_repeat(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0021_branching_base")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
