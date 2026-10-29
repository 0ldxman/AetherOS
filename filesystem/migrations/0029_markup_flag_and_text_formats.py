"""Поле page это «текст разбирается разметкой» (markup); форматы app и log из 0024 и 0027 не создались (имена занимали
сидеры 0008 и 0010), поэтому исправляются здесь; текстовые форматы можно править."""
from django.db import migrations, models


def fix_formats(apps, schema_editor):
    Format = apps.get_model("filesystem", "FileFormat")
    Format.objects.filter(name="app").update(
        title="APP application", extension=".app", kind="text", magic="", template="{body}", content="text", editable=True,
    )
    Format.objects.filter(name="log").update(
        title="LOG authentication log", extension=".log", kind="text", magic="", template="{body}", content="none", editable=False,
    )
    Format.objects.filter(kind="text", content__in=("text", "text_asset")).update(editable=True)


class Migration(migrations.Migration):
    dependencies = [("filesystem", "0028_instance_needs_host")]
    operations = [
        migrations.RenameField("fileformat", "page", "markup"),
        migrations.AlterField(
            "fileformat", "markup",
            field=models.BooleanField(
                default=False, verbose_name="Разбирать разметкой",
                help_text="Текст этого формата записан разметкой (::map, ::section, врезка): парсер рисует виджеты страницы, а в байтах файла "
                          "превращает их в то, что есть у формата. Остальные форматы остаются простым текстом.",
            ),
        ),
        migrations.RunPython(fix_formats, migrations.RunPython.noop),
    ]
