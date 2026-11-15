from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("machines", "0050_profile_endpoints")]

    operations = [
        migrations.AddField(model_name="machine", name="maintenance_text",
                            field=models.CharField(blank=True, max_length=255, verbose_name="Текст обслуживания",
                                                   help_text="Что видит игрок, когда машина на обслуживании (статус Maintenance) и вход закрыт. Пусто: system under maintenance.")),
    ]
