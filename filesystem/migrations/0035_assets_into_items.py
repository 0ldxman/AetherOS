"""Таблица ассетов уходит: файл в хранилище становится содержимым самого объекта.

Объекты, на которые ссылался ассет, получают его файл. Первый из них берёт публичный адрес ассета (старые ссылки /view/<адрес>/ живут)
и, если слаг ассета свободен, его слаг (так не ломаются ссылки из вики). Ассет без объектов становится объектом без размещения.
Вложения писем, которые смотрели на ассет, смотрят на этот объект.
"""
import posixpath
import uuid

from django.db import migrations
from django.utils.text import slugify

FILE_FORMATS = ("text_asset", "asset", "link_asset")


def free_slug(Item, base):
    base = (slugify(base) or "file")[:56]
    slug, number = base, 1
    while Item.objects.filter(slug=slug).exists():
        number += 1
        slug = f"{base}-{number}"
    return slug


def clean_name(text):
    for bad in ("/", "\\", ":"):
        text = text.replace(bad, "-")
    return (text.strip() or "file")[:200]


def forward(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    Item = apps.get_model("filesystem", "Item")
    FileFormat = apps.get_model("filesystem", "FileFormat")
    Attachment = apps.get_model("mail", "Attachment")

    for item in Item.objects.filter(public_id=None):
        item.public_id = uuid.uuid4()
        item.save(update_fields=["public_id"])

    for asset in Asset.objects.order_by("pk"):
        fields = {"file_id": asset.file_id, "file_name": asset.filename, "file_type": asset.content_type, "file_size": asset.size}
        items = list(Item.objects.filter(asset=asset).order_by("pk"))
        for item in items:
            for key, value in fields.items():
                setattr(item, key, value)
        if items:
            first = items[0]
            first.public_id = asset.public_id
            if asset.slug and first.slug != asset.slug and not Item.objects.filter(slug=asset.slug).exists():
                first.slug = asset.slug
            for item in items:
                item.save()
            target = first
        else:
            extension = posixpath.splitext(asset.filename or "")[1].lower()
            found = FileFormat.objects.filter(extension=extension, content__in=FILE_FORMATS).first() if extension else None
            target = Item.objects.create(
                slug=free_slug(Item, asset.slug or f"asset-{str(asset.public_id)[:8]}"), name=clean_name(asset.name), format=found.name if found else "",
                public_id=asset.public_id, **fields,
            )
        Attachment.objects.filter(asset=asset).update(item=target)


class Migration(migrations.Migration):

    dependencies = [
        ("filesystem", "0034_item_file_fields"),
        ("assets", "0007_asset_slug_and_file_metadata"),
        ("mail", "0011_storage_commands"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
