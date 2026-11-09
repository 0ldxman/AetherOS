from django.db import migrations


class Migration(migrations.Migration):
    """Поле «системный» у тома не прижилось: том отличий теперь назначает машина (Machine.overlay)."""

    dependencies = [
        ("filesystem", "0032_volume_system"),
    ]

    operations = [
        migrations.RemoveField(model_name="volume", name="system"),
    ]
