from django.db import migrations, models


def full_role(apps, schema_editor):
    """Роль «Полный доступ»: её получают авторы, которые уже были в команде до ролей."""
    Role = apps.get_model("team", "Role")
    sections = ["disks", "items", "machines", "formats", "policies", "systems", "scenes", "world", "map", "players"]
    Role.objects.get_or_create(name="Полный доступ", defaults={
        "note": "Всё, кроме управления командой.",
        "rights": {section: "edit" for section in sections},
        "actions": ["ban", "delete", "keys", "players", "reset"],
    })


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, unique=True, verbose_name="Название")),
                ("note", models.TextField(blank=True, verbose_name="Заметка")),
                ("rights", models.JSONField(blank=True, default=dict, help_text="{раздел: none|read|edit}", verbose_name="Права по разделам")),
                ("actions", models.JSONField(blank=True, default=list, verbose_name="Действия")),
            ],
            options={"ordering": ["name"], "verbose_name": "Роль", "verbose_name_plural": "Роли"},
        ),
        migrations.RunPython(full_role, migrations.RunPython.noop),
    ]
