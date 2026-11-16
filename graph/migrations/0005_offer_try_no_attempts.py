from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("graph", "0004_offers")]

    operations = [
        migrations.RemoveField(model_name="offertry", name="used"),
        migrations.AlterModelOptions(name="offertry", options={"verbose_name": "Закрытая игроку возможность",
                                                               "verbose_name_plural": "Закрытые игрокам возможности"}),
    ]
