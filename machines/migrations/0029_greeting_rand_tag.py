from django.db import migrations


def rename(apps, schema_editor):
    SystemType = apps.get_model("machines", "SystemType")
    for row in SystemType.objects.filter(greeting__contains="random>"):
        row.greeting = row.greeting.replace("<random>", "<rand>").replace("</random>", "</rand>")
        row.save(update_fields=["greeting"])


class Migration(migrations.Migration):
    dependencies = [("machines", "0028_machine_greeting_fields")]
    operations = [migrations.RunPython(rename, migrations.RunPython.noop)]
