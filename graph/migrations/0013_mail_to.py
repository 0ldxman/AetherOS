from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import mail_to

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if mail_to(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0012_each_boxes")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
