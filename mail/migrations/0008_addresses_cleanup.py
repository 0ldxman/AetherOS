from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("machines", "0006_profile_mail"),
        ("mail", "0007_addresses_data"),
    ]

    operations = [
        migrations.AlterModelOptions(name="composetask", options={"ordering": ("profile", "id")}),
        migrations.RemoveField(model_name="composetask", name="machine"),
        migrations.RemoveField(model_name="composetask", name="login"),
        migrations.RemoveField(model_name="composetask", name="to_login"),
        migrations.AlterField(
            model_name="composetask",
            name="profile",
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="compose_tasks", to="machines.machineprofile", verbose_name="От чьего имени"),
        ),
        migrations.RemoveField(model_name="message", name="machine"),
        migrations.RemoveField(model_name="message", name="to_login"),
        migrations.RemoveField(model_name="message", name="sender_login"),
        migrations.RemoveField(model_name="message", name="is_draft"),
        migrations.RemoveField(model_name="message", name="status_note"),
        migrations.RemoveField(model_name="message", name="delivery"),
        migrations.RemoveField(model_name="message", name="sender_name"),
        migrations.RemoveField(model_name="message", name="sender_address"),
        migrations.CreateModel(
            name="Trashed",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="trashed", to="mail.message")),
                ("profile", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="trashed_mail", to="machines.machineprofile")),
            ],
            options={"verbose_name": "письмо в корзине", "verbose_name_plural": "корзина профилей"},
        ),
        migrations.AddConstraint(
            model_name="trashed",
            constraint=models.UniqueConstraint(fields=("message", "profile"), name="unique_mail_trashed"),
        ),
    ]
