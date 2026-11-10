import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("filesystem", "0035_assets_into_items")]

    operations = [
        migrations.RemoveField(model_name="item", name="asset"),
        migrations.AlterField(
            model_name="item", name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, help_text="Адрес окна просмотра файла: /view/<адрес>/.", unique=True, verbose_name="Публичный адрес"),
        ),
    ]
