from django.db import migrations, models

import mail.addresses


class Migration(migrations.Migration):

    dependencies = [
        ("machines", "0006_profile_mail"),
        ("mail", "0005_compose_tasks"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="sender",
            field=models.CharField(default="", max_length=255, validators=[mail.addresses.validate_address], verbose_name="Отправитель"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="message",
            name="recipients",
            field=models.TextField(blank=True, default="", validators=[mail.addresses.validate_masks], verbose_name="Получатели"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="message",
            name="status",
            field=models.CharField(choices=[("ok", "Отправлено"), ("draft", "Черновик")], default="ok", max_length=8, verbose_name="Статус"),
        ),
        migrations.AddField(
            model_name="composetask",
            name="profile",
            field=models.ForeignKey(null=True, on_delete=models.deletion.CASCADE, related_name="compose_tasks", to="machines.machineprofile", verbose_name="От чьего имени"),
        ),
        migrations.AddField(
            model_name="composetask",
            name="recipients",
            field=models.TextField(blank=True, default="", verbose_name="Кому"),
            preserve_default=False,
        ),
    ]
