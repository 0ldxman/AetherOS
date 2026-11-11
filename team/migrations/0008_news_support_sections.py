from django.db import migrations


def grant(apps, schema_editor):
    """Новые разделы «Новости» и «Поддержка»: роль «Полный доступ» правит и их."""
    Role = apps.get_model("team", "Role")
    for role in Role.objects.filter(name="Полный доступ"):
        role.rights = {**(role.rights or {}), "news": "edit", "support": "edit"}
        role.save(update_fields=["rights"])


class Migration(migrations.Migration):
    dependencies = [("team", "0007_mail_section")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
