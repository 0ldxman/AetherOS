import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("team", "0005_board"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Название")),
                ("body", models.TextField(blank=True, verbose_name="Описание")),
                ("status", models.CharField(choices=[("open", "Открыта"), ("doing", "В работе"), ("review", "На проверке"), ("done", "Готово")], db_index=True, default="open", max_length=16, verbose_name="Статус")),
                ("priority", models.PositiveSmallIntegerField(default=5, help_text="1–10, 10 самый высокий", verbose_name="Приоритет")),
                ("due", models.DateField(blank=True, null=True, verbose_name="Срок")),
                ("labels", models.JSONField(blank=True, default=list, verbose_name="Метки")),
                ("links", models.JSONField(blank=True, default=list, help_text="[{target, kind, label, link}]", verbose_name="Сущности")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assignees", models.ManyToManyField(blank=True, related_name="tasks", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_tasks", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-priority", "due", "pk"], "verbose_name": "Задача", "verbose_name_plural": "Задачи"},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=16)),
                ("text", models.CharField(max_length=300)),
                ("link", models.CharField(blank=True, max_length=255)),
                ("key", models.CharField(max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-pk"], "verbose_name": "Уведомление", "verbose_name_plural": "Уведомления",
                     "constraints": [models.UniqueConstraint(fields=("user", "key"), name="unique_notification_key")]},
        ),
    ]
