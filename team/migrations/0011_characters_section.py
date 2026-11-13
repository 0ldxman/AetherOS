from django.db import migrations


def grant(apps, schema_editor):
    """Новый раздел «Персонажи»: роль «Полный доступ» правит и его."""
    Role = apps.get_model("team", "Role")
    for role in Role.objects.filter(name="Полный доступ"):
        role.rights = {**(role.rights or {}), "characters": "edit"}
        role.save(update_fields=["rights"])


class Migration(migrations.Migration):
    dependencies = [("team", "0010_forum_section")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
