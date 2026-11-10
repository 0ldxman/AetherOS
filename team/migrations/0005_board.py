import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def main_board(apps, schema_editor):
    Board = apps.get_model("team", "Board")
    if not Board.objects.filter(main=True).exists():
        Board.objects.create(title="Основная доска", main=True)


class Migration(migrations.Migration):
    dependencies = [
        ("team", "0004_draft"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Board",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120, verbose_name="Название")),
                ("main", models.BooleanField(default=False, verbose_name="Основная")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="boards", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-main", "title"], "verbose_name": "Доска", "verbose_name_plural": "Доски"},
        ),
        migrations.RunPython(main_board, migrations.RunPython.noop),
    ]
