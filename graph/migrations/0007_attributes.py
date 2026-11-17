from django.db import migrations


def forward(apps, schema_editor):
    from graph.upgrade import attributes

    Graph = apps.get_model("graph", "Graph")
    for graph in Graph.objects.all():
        if attributes(graph.doc):
            graph.save(update_fields=["doc"])


class Migration(migrations.Migration):
    dependencies = [("graph", "0006_offer_for_account")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
