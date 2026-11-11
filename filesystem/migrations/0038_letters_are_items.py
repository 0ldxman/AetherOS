from django.db import migrations

LETTER = "Письмо: заголовки (From, To, Subject, Date…), пустая строка и текст"


def letters_are_text(apps, schema_editor):
    """Письмо это объект формата msg, его текст и есть письмо целиком (заголовки и тело): байты файла это текст."""
    FileFormat = apps.get_model("filesystem", "FileFormat")
    FileFormat.objects.filter(name="msg").update(template="{body}", content="text", title="MSG письмо")


class Migration(migrations.Migration):
    dependencies = [
        ("filesystem", "0037_app_icons"),
        ("mail", "0012_attachment_asset_removed"),
    ]

    operations = [
        migrations.RemoveField(model_name="item", name="message"),
        migrations.RunPython(letters_are_text, migrations.RunPython.noop),
    ]
