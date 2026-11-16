from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Позывной переезжает с игрока на учётку (прежние позывные удаляются: прод не учитываем); модерация игрока — AirStanding."""

    dependencies = [
        ("air", "0006_engine_actions"),
        ("machines", "0054_sessions_live_workplace"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(lambda apps, schema: (apps.get_model("air", "CallsignChange").objects.all().delete(),
                                                   apps.get_model("air", "Callsign").objects.all().delete()), migrations.RunPython.noop),
        migrations.RemoveField(model_name="callsign", name="user"),
        migrations.AddField(model_name="callsign", name="profile", field=models.OneToOneField(
            default=0, on_delete=django.db.models.deletion.CASCADE, related_name="callsign", to="machines.machineprofile"), preserve_default=False),
        migrations.AlterField(model_name="callsign", name="rx_only", field=models.BooleanField(
            default=False, help_text="Передатчик учётки отобран: с неё слушают, но не передают.", verbose_name="Только приём")),
        migrations.RemoveField(model_name="callsignchange", name="user"),
        migrations.AddField(model_name="callsignchange", name="profile", field=models.ForeignKey(
            default=0, on_delete=django.db.models.deletion.CASCADE, related_name="callsign_changes", to="machines.machineprofile"), preserve_default=False),
        migrations.CreateModel(name="AirStanding", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("muted_until", models.DateTimeField(blank=True, null=True, verbose_name="Заглушён до")),
            ("rx_only", models.BooleanField(default=False, help_text="Передатчик отобран: игрок слушает, но не передаёт ни с какой учётки.", verbose_name="Только приём")),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="air_standing", to=settings.AUTH_USER_MODEL)),
        ]),
    ]
