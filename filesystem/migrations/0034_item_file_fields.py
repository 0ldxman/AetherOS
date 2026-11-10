import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("filesystem", "0033_remove_volume_system"),
        ("assets", "0007_asset_slug_and_file_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="item", name="file_id",
            field=models.CharField(blank=True, db_index=True, help_text="ID файла в Nextcloud (папка AETHER).", max_length=255, verbose_name="Файл в хранилище"),
        ),
        migrations.AddField(model_name="item", name="file_name", field=models.CharField(blank=True, editable=False, max_length=255, verbose_name="Имя файла")),
        migrations.AddField(model_name="item", name="file_type", field=models.CharField(blank=True, editable=False, max_length=127, verbose_name="Тип файла")),
        migrations.AddField(model_name="item", name="file_size", field=models.PositiveBigIntegerField(blank=True, editable=False, null=True, verbose_name="Размер файла")),
        migrations.AddField(model_name="item", name="public_id", field=models.UUIDField(editable=False, null=True, verbose_name="Публичный адрес")),
    ]
