from django.db import migrations


def grant(apps, schema_editor):
    """Новый раздел «Эфир»: роль «Полный доступ» правит и его."""
    Role = apps.get_model("team", "Role")
    for role in Role.objects.filter(name="Полный доступ"):
        role.rights = {**(role.rights or {}), "air": "edit"}
        role.save(update_fields=["rights"])


class Migration(migrations.Migration):
    dependencies = [("team", "0008_news_support_sections")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
