import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("team", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Change",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Когда")),
                ("username", models.CharField(max_length=150, verbose_name="Имя автора")),
                ("method", models.CharField(max_length=8)),
                ("path", models.CharField(db_index=True, max_length=512, verbose_name="Путь")),
                ("section", models.CharField(blank=True, db_index=True, max_length=32, verbose_name="Раздел")),
                ("action", models.CharField(max_length=16, verbose_name="Действие")),
                ("kind", models.CharField(blank=True, max_length=64, verbose_name="Вид")),
                ("label", models.CharField(blank=True, max_length=200, verbose_name="Что")),
                ("link", models.CharField(blank=True, max_length=255, verbose_name="Ссылка в Студии")),
                ("summary", models.CharField(blank=True, max_length=200, verbose_name="Что именно")),
                ("snapshot", models.JSONField(blank=True, null=True, verbose_name="Снимок до удаления")),
                ("user", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="changes",
                                           to=settings.AUTH_USER_MODEL, verbose_name="Автор")),
            ],
            options={"ordering": ["-pk"], "verbose_name": "Изменение", "verbose_name_plural": "Лента изменений"},
        ),
    ]
