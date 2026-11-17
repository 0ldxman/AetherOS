from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import events

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if events(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0008_wrote_outs")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
