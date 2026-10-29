"""Помощники для тестов: файлы машины и ключи игрока так, как они устроены в игре (тома, объекты, слой игрока)."""
import posixpath
from types import SimpleNamespace

from django.utils.text import slugify

from filesystem import keystore
from filesystem.content.archives import has_extension
from filesystem.manager.filemanager import unique_slug
from filesystem.machine_view import MachineView
from filesystem.models import KEY_FORMAT, Item, ItemKey, ItemMember, Placement, Volume
from machines.models import MachineMount, Place


def root_volume(machine):
    """Том, смонтированный на корень машины (создаётся при первом обращении): в нём лежат файлы, созданные make_file."""
    from filesystem.manager.provision import ensure_root

    volume = ensure_root(machine)
    Place.objects.get_or_create(machine=machine, name="secrets", defaults={"path": "/home/.secrets"})     # у тестов одна папка секретов
    return volume


def _folder(volume, parent, name):
    found = Placement.objects.filter(volume=volume, parent=parent, name=name).first()
    if found is None:
        return Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.FOLDER, name=name)
    return found


PAGE_EXT = {"doc": ".doc", "scan": ".scan", "web": ".snp", "rec": ".rec"}


def page_slug(path):
    return "wiki-" + path.replace("/", "-")


def make_page(path, type="doc", body="", access=None, created_by=None, **fields):
    """Страница, на которую ссылается адрес `apps/wiki/<путь>` в make_file (путь: Раздел/Название)."""
    from filesystem.content.rawview.registry import format_for_extension

    name = path.rsplit("/", 1)[-1]
    return Item.objects.create(
        slug=page_slug(path), name=name, format=format_for_extension(PAGE_EXT[type]).name, body=body, access=access or {},
        world_creator=created_by.get_username() if created_by else "", **fields,
    )


def _item_for(name, state, size, body, format, key, url):
    """Объект для файла. url: адрес содержимого в старом виде (записи вики, ключ, ассет, карта, письмо) для тестов, которые его ещё
    называют: запись вики копируется в объект, остальное связывается с тем, на что указывает."""
    import uuid as uuidlib

    if key or (url or "").startswith("keys/"):
        slug = key or url.split("/")[1]
        return Item.objects.get_or_create(slug=slug, defaults={"name": slug, "format": KEY_FORMAT, "body": body})[0]
    fields = {"state": state, "size": size, "body": body, "format": format}
    url = (url or "").strip()
    parts = [part for part in url.split("?")[0].split("/") if part]
    if parts[:2] == ["apps", "wiki"] and len(parts) >= 4:
        found = Item.objects.filter(slug=page_slug("/".join(parts[2:]))).first()
        if found is not None:
            return Item.objects.create(
                slug=unique_slug(f"wiki-{found.name}"), name=found.name, format=found.format, body=found.body, meta=found.meta,
                access=found.access, world_updated_at=found.world_updated_at, world_creator=found.world_creator, state=state, size=size,
            )
    elif parts[:1] == ["view"] and len(parts) >= 2:
        from assets.models import Asset

        asset = Asset.objects.filter(public_id=uuidlib.UUID(parts[1])).first()
        return Item.objects.create(slug=unique_slug(name), name=name, asset=asset, state=state, size=size)
    elif parts[:2] == ["apps", "map"]:
        from map.models import MapScene

        slug = url.split("scene=")[-1]
        return Item.objects.create(slug=unique_slug(name), name=name, scene=MapScene.objects.filter(slug=slug).first(), state=state, size=size)
    elif parts[:2] == ["apps", "mail"]:
        from mail.models import Message

        ref = url.split("message=")[-1]
        return Item.objects.create(slug=unique_slug(name), name=name, message=Message.objects.filter(slug=ref).first(), state=state, size=size)
    if parts[:1] == ["apps"]:                                                      # приложение как таковое: у файла есть окно
        return Item.objects.create(slug=unique_slug(name), name=name, url="https://example.com/" + "/".join(parts[1:]), state=state, size=size)
    return Item.objects.create(slug=unique_slug(name), name=name, **fields)


def make_file(machine, path, state="", size=None, system=False, directory=False, key=None, body="", format="", url="", file_type="FILE",
              **ignored):
    """Файл (или папка) машины по пути, как раньше создавалась запись MachineFile. Возвращает SimpleNamespace(item, placement, path).

    state слои защиты, size указанный размер, system защита от удаления, directory папка, key слаг ключа (файл-ключ), body текст.
    Путь с «архивом» (имя с расширением, под которым что-то лежит) делает архив: объект с членами, а файлы под ним его члены."""
    volume = root_volume(machine)
    directory = directory or file_type == "DIRECTORY"
    parts = [part for part in path.strip("/").split("/") if part]
    parent, depth = None, 0

    while depth < len(parts) - 1:                                                      # папки до файла; архив прерывает спуск
        name = parts[depth]
        folder = Placement.objects.filter(volume=volume, parent=parent, name=name).first()
        if folder is not None and folder.kind == Placement.Kind.ITEM:
            return _member(machine, volume, folder, parts[depth + 1:], state, size, body, format, key, url)
        if folder is None and has_extension(name):
            archive = Item.objects.create(slug=unique_slug(name), name=name)
            folder = Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.ITEM, item=archive, name=name)
            return _member(machine, volume, folder, parts[depth + 1:], state, size, body, format, key, url)
        parent = _folder(volume, parent, name) if folder is None else folder
        depth += 1

    name = parts[-1]
    existing = Placement.objects.filter(volume=volume, parent=parent, name=name).first()
    if directory:
        found = existing or Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.FOLDER, name=name)
        if system and not found.system:
            found.system = True
            found.save(update_fields=["system"])
        return SimpleNamespace(item=None, placement=found, path=path, pk=found.pk)

    if existing is not None and existing.kind == Placement.Kind.ITEM:                  # файл уже есть (архив, созданный членами)
        item = existing.item
        if state:
            item.state = state
        if size is not None:
            item.size = size
        item.save()
        if system:
            existing.system = True
            existing.save(update_fields=["system"])
        return SimpleNamespace(item=item, placement=existing, path=path, pk=item.pk)

    item = _item_for(name, state, size, body, format, key, url)
    placement = Placement.objects.create(
        volume=volume, parent=parent, kind=Placement.Kind.ITEM, item=item, name=name, system=system,
    )
    return SimpleNamespace(item=item, placement=placement, path=path, pk=item.pk)


def _member(machine, volume, archive_placement, rest, state, size, body, format, key, url=""):
    """Файл под путём архива: член архива. Вложенный архив (имя с расширением посреди пути) член-архив со своими членами."""
    archive = archive_placement.item
    inner, remaining = "", list(rest)
    while len(remaining) > 1:
        part = remaining.pop(0)
        if not has_extension(part):
            inner = f"{inner}/{part}" if inner else part
            continue
        path = f"{inner}/{part}" if inner else part
        row = ItemMember.objects.filter(archive=archive, path=path).first()
        nested = row.item if row is not None else Item.objects.create(slug=unique_slug(f"{archive.slug}-{part}"), name=part)
        if row is None:
            ItemMember.objects.create(archive=archive, path=path, item=nested)
        archive, inner = nested, ""
    leaf = remaining[0]
    path = f"{inner}/{leaf}" if inner else leaf
    existing = ItemMember.objects.filter(archive=archive, path=path).first()
    if existing is not None:                                                         # член уже есть (вложенный архив, созданный раньше)
        item = existing.item
        if state:
            item.state = state
        item.save()
        return SimpleNamespace(item=item, placement=archive_placement, path=f"{archive_placement.name}/{path}", pk=item.pk)
    item = _item_for(f"{archive.slug}-{leaf}", state, size, body, format, key, url)
    item.name = leaf
    item.save(update_fields=["name"])
    ItemMember.objects.create(archive=archive, path=path, item=item)
    return SimpleNamespace(item=item, placement=archive_placement, path=f"{archive_placement.name}/{path}", pk=item.pk)


def embed_key(item, slug):
    """Внедрить ключ slug в байты объекта (ItemKey); сам ключ объект формата key."""
    key, _ = Item.objects.get_or_create(slug=slug, defaults={"name": slug, "format": KEY_FORMAT})
    return ItemKey.objects.get_or_create(item=item, key=key)[0]


def key_item(slug, body="", name=""):
    """Объект-ключ с таким слагом (name: описание ключа, которое показывает ward keys)."""
    return Item.objects.get_or_create(slug=slug, defaults={"name": name or slug, "format": KEY_FORMAT, "body": body})[0]


def give_keys(user, *slugs):
    """Сессия игрока user с ключами slugs в папке секретов. Возвращает словарь сессии запроса (SESSION_KEY: id)."""
    from machines.current import SESSION_KEY
    from machines.models import Machine, MachineProfile, Session

    session = Session.objects.filter(user=user).order_by("-pk").first()          # уже начатая игроком сессия
    if session is None:
        machine = Machine.objects.create(name=f"keys-{user.pk}", hostname=f"keys-{user.pk}")
        profile = MachineProfile.objects.create(machine=machine, user=user, name=user.get_username(), login="keys", freq=1)
        session = Session.objects.create(user=user, profile=profile)
        from filesystem.models import Volume

        # вики машины видна целиком, кроме корней других машин: иначе файл вики этой машины снёс бы чужой (remove_apps_named)
        wiki_sections(machine, list(Volume.objects.exclude(mounts__mount_path="/").order_by("pk")))
    machine = session.profile.machine
    root_volume(machine)
    view = MachineView(machine, user)
    for slug in slugs:
        keystore.put(view, machine, session.profile.login, key_item(slug))
    return {SESSION_KEY: session.pk}


def give_key_to_session(session, slug):
    """Положить ключ slug в папку секретов записи этой сессии (как после kex)."""
    machine = session.profile.machine
    root_volume(machine)
    return keystore.put(MachineView(machine, session.user), machine, session.profile.login, key_item(slug))


APPS_DIR = "/apps-desktop"


def wiki_sections(machine, volumes):
    """Вики на машине: каждый том монтируется в /wiki/<слаг>, а файл вики называет его разделом (по порядку списка)."""
    from machines.models import MachineMount

    lines = []
    for order, volume in enumerate(volumes):
        MachineMount.objects.get_or_create(machine=machine, mount_path=f"/wiki/{volume.slug}", defaults={"volume": volume, "order": order})
        lines.append(f"/wiki/{volume.slug} as {volume.name or volume.slug}")
    remove_apps_named(machine, "wiki")
    return make_app(machine, "wiki", "W", "/apps/wiki/", volumes=lines)


def remove_apps_named(machine, label):
    from filesystem.models import Placement

    found = Placement.objects.filter(name=f"{label}.app", volume__mounts__machine=machine)
    items = list(found.values_list("item_id", flat=True))
    found.delete()
    Item.objects.filter(pk__in=items).delete()


def make_app(machine, label, glyph, path, suffix="", key_condition=None, order=0, volumes=()):
    """Иконка на столе машины: файл приложения в общем месте desktop (у машины оно одно на всех записей)."""
    from filesystem import appfile

    Place.objects.get_or_create(machine=machine, name="desktop", defaults={"path": APPS_DIR})
    made = make_file(machine, f"{APPS_DIR}/{label}.app", body=appfile.render(label, glyph, path, suffix, order, volumes), format="app")
    if key_condition:
        made.item.access = key_condition
        made.item.save(update_fields=["access"])
    return made


def remove_apps(machine=None):
    """Убрать со стола все иконки (машины или всех)."""
    found = Placement.objects.filter(item__format="app")
    if machine is not None:
        found = found.filter(volume__mounts__machine=machine)
    items = list(found.values_list("item_id", flat=True))
    found.delete()
    Item.objects.filter(pk__in=items).delete()
