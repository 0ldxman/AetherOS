
import uuid

from django.db import migrations


def fix_public_ids(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    db_alias = schema_editor.connection.alias

    seen = set()

    assets = (
        Asset.objects.using(db_alias)
        .filter(public_id__isnull=False)
        .order_by("pk")
    )

    for asset in assets.iterator():
        if asset.public_id in seen:
            new_id = uuid.uuid4()

            while new_id in seen:
                new_id = uuid.uuid4()

            asset.public_id = new_id
            asset.save(update_fields=["public_id"])
            seen.add(new_id)
        else:
            seen.add(asset.public_id)

    # Заполняем отсутствующие UUID.
    for asset in (
        Asset.objects.using(db_alias)
        .filter(public_id__isnull=True)
        .iterator()
    ):
        new_id = uuid.uuid4()

        while new_id in seen:
            new_id = uuid.uuid4()

        asset.public_id = new_id
        asset.save(update_fields=["public_id"])
        seen.add(new_id)


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0002_asset_public_id_asset_viewer_type"),
    ]

    operations = [
        migrations.RunPython(
            fix_public_ids,
            migrations.RunPython.noop,
        ),
    ]
