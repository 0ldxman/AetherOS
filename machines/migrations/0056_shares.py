from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("machines", "0055_mount_read_only")]

    operations = [
        migrations.CreateModel(
            name="Share",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, verbose_name="Имя")),
                ("path", models.CharField(max_length=2048, verbose_name="Папка")),
                ("code", models.CharField(max_length=32, verbose_name="Код")),
                ("mode", models.CharField(choices=[("ro", "Только чтение"), ("drop", "Класть новое")], default="ro", max_length=8, verbose_name="Режим")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shares", to="machines.machine")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shares", to="machines.machineprofile", verbose_name="Учётка")),
            ],
            options={"verbose_name": "Раздача", "verbose_name_plural": "Раздачи", "ordering": ("machine", "name")},
        ),
        migrations.AddConstraint(model_name="share", constraint=models.UniqueConstraint(fields=("machine", "name"), name="unique_share_name")),
        migrations.AlterField(model_name="playermount", name="secret", field=models.CharField(
            blank=True, help_text="Код раздачи в момент подключения: сменился, диск пропал.", max_length=128, verbose_name="Отпечаток пароля")),
        migrations.AddField(model_name="playermount", name="share", field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="mounts", to="machines.share", verbose_name="Раздача")),
    ]
