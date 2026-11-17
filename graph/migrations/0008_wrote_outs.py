from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import wrote_outs

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if wrote_outs(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0007_attributes")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
