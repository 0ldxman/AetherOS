from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("world", "0006_drop_flags_counters"), ("machines", "0054_sessions_live_workplace")]

    operations = [
        migrations.RunPython(lambda apps, schema: apps.get_model("world", "WorldLetterDelivery").objects.all().delete(), migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="worldletterdelivery", name="unique_world_letter_user"),
        migrations.RemoveField(model_name="worldletterdelivery", name="user"),
        migrations.AddField(model_name="worldletterdelivery", name="profile", field=models.ForeignKey(default=0, on_delete=django.db.models.deletion.CASCADE, related_name="+", to="machines.machineprofile"), preserve_default=False),
        migrations.AddConstraint(model_name="worldletterdelivery", constraint=models.UniqueConstraint(fields=("letter", "profile"), name="unique_world_letter_profile")),
    ]
