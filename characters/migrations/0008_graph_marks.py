from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("characters", "0007_drop_tags")]

    operations = [
        migrations.AddField(model_name="inbound", name="graph", field=models.CharField(
            blank=True, help_text="Слаг сценария, который ответил на сообщение.", max_length=64, verbose_name="Сценарий")),
        migrations.AddField(model_name="reply", name="graph", field=models.CharField(
            blank=True, help_text="Слаг сценария, который отправил реплику.", max_length=64, verbose_name="Сценарий")),
    ]
