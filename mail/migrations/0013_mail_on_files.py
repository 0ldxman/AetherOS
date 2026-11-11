import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Почта переезжает в файлы машин: старые письма, вложения, доставки, корзина и задачи на набор удаляются
    (в рабочей базе были только два тестовых письма)."""

    dependencies = [
        ("mail", "0012_attachment_asset_removed"),
        ("filesystem", "0038_letters_are_items"),
        ("machines", "__latest__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name="ComposeProgress"),
        migrations.DeleteModel(name="ComposeTask"),
        migrations.DeleteModel(name="Attachment"),
        migrations.DeleteModel(name="Delivered"),
        migrations.DeleteModel(name="MessageRead"),
        migrations.DeleteModel(name="Trashed"),
        migrations.DeleteModel(name="Message"),
        migrations.CreateModel(
            name="MailMark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(max_length=1024, verbose_name="Путь письма")),
                ("session_key", models.CharField(blank=True, max_length=64)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("arrived_at", models.DateTimeField(blank=True, help_text="Время машины игрока, когда письмо пришло.", null=True)),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mail_marks", to="machines.machine")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="mail_marks", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Отметка письма", "verbose_name_plural": "Отметки писем"},
        ),
        migrations.AddConstraint(model_name="mailmark", constraint=models.UniqueConstraint(fields=("machine", "path", "user", "session_key"), name="unique_mail_mark")),
        migrations.AddIndex(model_name="mailmark", index=models.Index(fields=["user", "machine"], name="mailmark_user_machine_idx")),
        migrations.CreateModel(
            name="MailQueue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folder", models.CharField(default="inbox", max_length=16)),
                ("available_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mail_queue", to="filesystem.item")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mail_queue", to="machines.machineprofile")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mail_queue", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("available_at", "pk"), "verbose_name": "Письмо в очереди", "verbose_name_plural": "Очередь писем"},
        ),
    ]
