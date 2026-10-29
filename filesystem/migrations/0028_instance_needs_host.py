"""У экземпляра тома всегда есть хост: «внешних» экземпляров без машины больше нет (сетевое подключение ходит к хосту)."""
import django.db.models.deletion
from django.db import migrations, models


def drop_external(apps, schema_editor):
    apps.get_model("filesystem", "VolumeInstance").objects.filter(host__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("filesystem", "0027_log_format"),
        ("machines", "0024_event_index"),
    ]

    operations = [
        migrations.RunPython(drop_external, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="volumeinstance", name="unique_instance_external"),
        migrations.RemoveConstraint(model_name="volumeinstance", name="unique_instance_host"),
        migrations.AlterField(
            model_name="volumeinstance", name="host",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hosted_volumes", to="machines.machine"),
        ),
        migrations.AddConstraint(
            model_name="volumeinstance", constraint=models.UniqueConstraint(fields=("volume", "host"), name="unique_instance_host"),
        ),
    ]
