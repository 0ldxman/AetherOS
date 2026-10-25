from django.db import migrations, models

import mail.addresses


def fill_mail(apps, schema_editor):
    Profile = apps.get_model("machines", "MachineProfile")
    for profile in Profile.objects.select_related("machine"):
        host = profile.machine.hostname or profile.machine.name
        profile.mail = f"{profile.login}@{host}"
        profile.save(update_fields=["mail"])


class Migration(migrations.Migration):

    dependencies = [
        ("machines", "0005_mailboxes"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineprofile",
            name="mail",
            field=models.CharField(
                default="",
                help_text="Адрес этого профиля, например will_smith@apollo.mail. Игрок под профилем читает и пишет от его лица.",
                max_length=255,
                validators=[mail.addresses.validate_address],
                verbose_name="Почта",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(fill_mail, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="machine",
            name="mail_domain",
        ),
    ]
