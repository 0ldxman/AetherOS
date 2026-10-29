"""Помощники для тестов вики: разделы и страницы на томах (раньше это были Namespace и Document)."""
from types import SimpleNamespace

from filesystem.manager.filemanager import unique_slug
from filesystem.models import Item, Placement, Volume
from filesystem.content.rawview.registry import format_for_extension

TYPE_EXT = {"doc": ".doc", "scan": ".scan", "web": ".snp", "rec": ".rec"}


def make_namespace(name, parent=None, slug="", access=None, hidden=False, **ignored):
    """Раздел: корневой это том, вложенный папка в томе родителя. Возвращает SimpleNamespace(pk, name, volume, placement, parent)."""
    if parent is None:
        volume = Volume.objects.create(slug=slug or unique_slug(name, Volume.objects), name=name, access=access or {})
        return SimpleNamespace(pk=-volume.pk, name=name, volume=volume, placement=None, parent=None, path=lambda: name)
    placement = Placement.objects.create(
        volume=parent.volume, parent=parent.placement, kind=Placement.Kind.FOLDER, name=name, access=access or {}, hidden=hidden,
    )
    return SimpleNamespace(pk=placement.pk, name=name, volume=parent.volume, placement=placement, parent=parent,
                           path=lambda: f"{parent.path()}:{name}")


def make_document(namespace, title, type="doc", body="", infobox="", direct_link="", access=None, hidden=False, world_date=None,
                  created_by=None, **ignored):
    """Страница вики: объект формата записи, положенный в раздел. Возвращает SimpleNamespace(pk, item, placement, title, ...)."""
    found = format_for_extension(TYPE_EXT[type])
    item = Item.objects.create(
        slug=direct_link or unique_slug(title), name=title, format=found.name, body=body, meta=infobox, access=access or {},
        world_updated_at=world_date, world_creator=created_by.get_username() if created_by else "",
    )
    placement = Placement.objects.create(
        volume=namespace.volume, parent=namespace.placement, kind=Placement.Kind.ITEM, item=item, name=item.default_filename, hidden=hidden,
    )
    return SimpleNamespace(pk=placement.pk, item=item, placement=placement, title=title, namespace=namespace, direct_link=item.slug)
