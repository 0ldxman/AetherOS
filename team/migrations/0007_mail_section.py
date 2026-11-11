from django.db import migrations


def grant(apps, schema_editor):
    """Новый раздел «Почта»: роль «Полный доступ» правит и его."""
    Role = apps.get_model("team", "Role")
    for role in Role.objects.filter(name="Полный доступ"):
        role.rights = {**(role.rights or {}), "mail": "edit"}
        role.save(update_fields=["rights"])


class Migration(migrations.Migration):
    dependencies = [("team", "0006_task_notification")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
