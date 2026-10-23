import django.core.validators
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0006_alter_asset_viewer_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="slug",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Для ссылок из вики: ::asset slug",
                max_length=64,
                validators=[
                    django.core.validators.RegexValidator(
                        message=(
                            "Только строчные латинские буквы, цифры, "
                            "«-» и «_»; начинаться нужно с буквы или цифры."
                        ),
                        regex="^[a-z0-9][a-z0-9_-]*$",
                    )
                ],
                verbose_name="Slug",
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="filename",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                max_length=255,
                verbose_name="File name",
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="content_type",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                max_length=127,
                verbose_name="Content type",
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="size",
            field=models.PositiveBigIntegerField(
                blank=True,
                editable=False,
                null=True,
                verbose_name="Size (bytes)",
            ),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.UniqueConstraint(
                condition=~Q(slug=""),
                fields=("slug",),
                name="assets_asset_unique_slug",
            ),
        ),
    ]