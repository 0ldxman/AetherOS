from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("machines", "0054_sessions_live_workplace")]

    operations = [
        migrations.AddField(model_name="machinemount", name="read_only", field=models.BooleanField(
            default=False, help_text="Игрок не может ничего записать, изменить или удалить на этом диске.", verbose_name="Только чтение")),
    ]
