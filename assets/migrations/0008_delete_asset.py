from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0007_asset_slug_and_file_metadata"),
        ("filesystem", "0036_item_asset_removed"),
        ("mail", "0012_attachment_asset_removed"),
    ]

    operations = [migrations.DeleteModel(name="Asset")]
