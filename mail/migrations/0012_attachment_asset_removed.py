import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mail", "0011_storage_commands"),
        ("filesystem", "0035_assets_into_items"),
    ]

    operations = [
        migrations.RemoveField(model_name="attachment", name="asset"),
        migrations.AlterField(
            model_name="attachment", name="item",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="mail_attachments", to="filesystem.item",
                help_text="Объект: для файла на машину (игрок сохраняет его к себе) или для файла из хранилища (объект с файлом в Nextcloud).",
            ),
        ),
    ]
