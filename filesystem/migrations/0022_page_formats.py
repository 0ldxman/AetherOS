from django.db import migrations

PAGE_FORMATS = ("doc", "scan", "snp", "rec")          # форматы записей вики: страница вики и текст, который можно править


def mark_pages(apps, schema_editor):
    apps.get_model("filesystem", "FileFormat").objects.filter(name__in=PAGE_FORMATS).update(page=True, editable=True)


class Migration(migrations.Migration):
    dependencies = [("filesystem", "0021_remove_machine_files")]
    operations = [migrations.RunPython(mark_pages, migrations.RunPython.noop)]
