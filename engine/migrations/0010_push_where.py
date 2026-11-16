from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("engine", "0009_condition_keys")]

    operations = [
        migrations.AddField(model_name="push", name="where", field=models.CharField(
            blank=True, max_length=32, verbose_name="Где",
            help_text="account:<номер> или machine:<номер>: показать, только когда стол (терминал — для терминальных) игрока там. Пусто — где угодно.")),
    ]
