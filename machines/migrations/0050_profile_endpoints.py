from decimal import Decimal

from django.db import migrations, models


def to_endpoints(apps, schema_editor):
    """Частота -> список точек; одинаковые логины на машине сливаются в одну учётку со всеми точками (лишние записи удаляются)."""
    Profile = apps.get_model("machines", "MachineProfile")
    kept = {}
    for row in Profile.objects.order_by("pk"):
        found = [f"{row.freq:.3f}"] if row.freq and Decimal(row.freq) != 0 else []
        key = (row.machine_id, row.login)
        if key in kept:
            first = kept[key]
            first.endpoints = sorted(set(first.endpoints) | set(found))
            first.save(update_fields=["endpoints"])
            row.delete()
            continue
        row.endpoints = found
        row.save(update_fields=["endpoints"])
        kept[key] = row


class Migration(migrations.Migration):
    dependencies = [("machines", "0049_alter_loginevent_kind")]

    operations = [
        migrations.AddField(model_name="machineprofile", name="endpoints",
                            field=models.JSONField(blank=True, default=list, verbose_name="Точки входа",
                                                   help_text="Где на учётку заходят удалённо: у систем Aether частоты в МГц (14.230), у остальных порты (22). Пусто — извне не зайти.")),
        migrations.RunPython(to_endpoints, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="machineprofile", name="unique_machine_profile_endpoint"),
        migrations.RemoveField(model_name="machineprofile", name="freq"),
        migrations.AlterModelOptions(name="machineprofile", options={"ordering": ("machine", "login")}),
        migrations.AddConstraint(model_name="machineprofile",
                                 constraint=models.UniqueConstraint(fields=("machine", "login"), name="unique_machine_profile_login")),
    ]
