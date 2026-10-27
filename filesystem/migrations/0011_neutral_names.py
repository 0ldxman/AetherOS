"""Названия форматов без «Aether»: файлы бывают на системах любых организаций. Меняются только записи, которые автор не трогал."""
from django.db import migrations

TITLES = {
    "rec": ("Aether REC (record)", "REC record"),
    "snp": ("Aether SNP (page snapshot)", "SNP page snapshot"),
    "msg": ("Aether MSG (message)", "MSG message"),
    "scan": ("Aether SCAN (image + OCR text)", "SCAN image + OCR text"),
    "doc": ("Aether DOC (package of parts)", "DOC package of parts"),
    "pak": ("Aether PAK (archive)", "PAK archive"),
    "app": ("Aether APP (application descriptor)", "APP application descriptor"),
    "log": ("Aether LOG (session log)", "LOG session log"),
    "map": ("Aether MAP (map scene)", "MAP map scene"),
}


def rename(apps, schema_editor):
    Format = apps.get_model("filesystem", "FileFormat")
    for name, (old, new) in TITLES.items():
        Format.objects.filter(name=name, title=old).update(title=new)
    for item in Format.objects.filter(kind="text", template__contains="@aether>"):
        item.template = item.template.replace("@aether>", "@{host}>")
        item.save(update_fields=["template"])


class Migration(migrations.Migration):

    dependencies = [
        ("filesystem", "0010_seed_more_formats"),
    ]

    operations = [
        migrations.RunPython(rename, migrations.RunPython.noop),
    ]
