from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("graph", "0005_offer_try_no_attempts"), ("machines", "0054_sessions_live_workplace")]

    operations = [
        migrations.AddField(model_name="offer", name="profile", field=models.ForeignKey(
            blank=True, help_text="Для учётки: видят все, кто на ней.", null=True, on_delete=django.db.models.deletion.CASCADE,
            related_name="+", to="machines.machineprofile")),
    ]
