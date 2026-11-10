import django.db.models.deletion
from django.db import migrations, models


def keep_access(apps, schema_editor):
    """Авторы, бывшие в команде до ролей, сохраняют полный доступ."""
    User = apps.get_model("users", "User")
    Role = apps.get_model("team", "Role")
    full = Role.objects.filter(name="Полный доступ").first()
    if full is not None:
        User.objects.filter(is_staff=True, is_superuser=False).update(role=full)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_drop_user_keys"),
        ("team", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="role",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="users",
                                    to="team.role", verbose_name="Роль в Студии"),
        ),
        migrations.RunPython(keep_access, migrations.RunPython.noop),
    ]
