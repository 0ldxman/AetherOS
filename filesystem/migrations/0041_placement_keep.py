from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("filesystem", "0040_file_changes_in_world")]

    operations = [
        migrations.AddField(model_name="placement", name="keep", field=models.BooleanField(
            default=False, help_text="Игрок не может удалить или перенести этот файл (улика остаётся для всех).", verbose_name="Не удалить")),
    ]
