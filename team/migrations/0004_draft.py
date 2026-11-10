from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("team", "0003_comment")]

    operations = [
        migrations.CreateModel(
            name="Draft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("room", models.CharField(max_length=512, unique=True, verbose_name="Комната")),
                ("state", models.BinaryField(verbose_name="Состояние Yjs")),
                ("dirty", models.BooleanField(db_index=True, default=False, verbose_name="Есть несохранённое")),
                ("editors", models.JSONField(blank=True, default=list, verbose_name="Кто правил")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Черновик", "verbose_name_plural": "Черновики"},
        ),
    ]
