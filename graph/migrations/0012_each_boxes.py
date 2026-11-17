from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import each_boxes

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if each_boxes(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0011_run_parent")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
