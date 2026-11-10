import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("team", "0002_change"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Comment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target", models.CharField(db_index=True, max_length=512, verbose_name="Сущность")),
                ("kind", models.CharField(blank=True, max_length=64, verbose_name="Вид")),
                ("label", models.CharField(blank=True, max_length=200, verbose_name="Что")),
                ("link", models.CharField(blank=True, max_length=255, verbose_name="Ссылка в Студии")),
                ("username", models.CharField(max_length=150, verbose_name="Имя автора")),
                ("text", models.TextField(verbose_name="Текст")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("edited_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_by", models.CharField(blank=True, max_length=150)),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="comments", to=settings.AUTH_USER_MODEL)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="replies", to="team.comment")),
                ("mentions", models.ManyToManyField(blank=True, related_name="mentioned_in", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at", "pk"], "verbose_name": "Комментарий", "verbose_name_plural": "Комментарии"},
        ),
    ]
