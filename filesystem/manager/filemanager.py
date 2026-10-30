"""Операции файлового менеджера над томом: то, что автор делает кнопками «как в проводнике».

Всё работает с размещениями (Placement): файл в томе это строка дерева, а объект (Item) живёт отдельно и может лежать в
нескольких местах. Ошибки это FileManagerError с готовым текстом для автора.
"""
import posixpath

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from filesystem.models import FileFormat, Item, Placement, Volume
from filesystem.names import validate_name


class FileManagerError(Exception):
    """Понятная автору причина, почему операция не выполнена."""


def clean_name(name):
    name = (name or "").strip()
    try:
        validate_name(name)
    except ValidationError as exc:
        raise FileManagerError(exc.messages[0])
    return name


def format_by_extension(extension):
    """Формат реестра по расширению (.txt, или псевдоним jpeg) или None."""
    wanted = (extension or "").strip().lower()
    if not wanted.startswith("."):
        wanted = "." + wanted
    exact = FileFormat.objects.filter(extension__iexact=wanted).first()
    if exact:
        return exact
    bare = wanted.lstrip(".")
    return next((found for found in FileFormat.objects.exclude(aliases="") if bare in [word.strip().lstrip(".").lower() for word in found.aliases.split(",")]), None)


def split_file_name(typed, format_name=""):
    """Что набрал автор -> (название объекта, формат). «notes.txt» даёт («notes», txt), «README» даёт («README», без формата)."""
    typed = clean_name(typed)
    if format_name:
        found = FileFormat.objects.filter(name=format_name).first()
        if found is None:
            raise FileManagerError("Такого формата нет в реестре.")
        if found.extension and typed.lower().endswith(found.extension.lower()):
            typed = typed[: -len(found.extension)] or typed
        return typed, found
    stem, extension = posixpath.splitext(typed)
    found = format_by_extension(extension) if extension and stem else None
    return (stem, found) if found else (typed, None)


def unique_slug(text, taken=Item.objects):
    base = slugify(text)[:50] or "item"
    slug, number = base, 1
    while taken.filter(slug=slug).exists():
        number += 1
        slug = f"{base}-{number}"
    return slug


def siblings(volume, parent):
    return Placement.objects.filter(volume=volume, parent=parent)


def check_free(volume, parent, name, ignore=None):
    taken = siblings(volume, parent).filter(name=name)
    if ignore is not None:
        taken = taken.exclude(pk=ignore)
    if taken.exists():
        raise FileManagerError(f"«{name}» уже есть в этой папке.")


def folder_of(volume, parent_id):
    """Папка тома по id (None: корень)."""
    if parent_id in (None, "", 0):
        return None
    found = Placement.objects.filter(pk=parent_id, volume=volume, kind=Placement.Kind.FOLDER).first()
    if found is None:
        raise FileManagerError("Такой папки нет.")
    return found


def depth_ok(parent):
    from filesystem.models import MAX_DEPTH

    if parent is not None and parent.depth() + 1 >= MAX_DEPTH:
        raise FileManagerError(f"Папки вложены не глубже {MAX_DEPTH} уровней.")


def data(volume):
    """Всё дерево тома для менеджера: размещения и список форматов (менеджер держит его у себя и рисует сам)."""
    rows = []
    for placement in volume.placements.select_related("item"):
        item = placement.item
        rows.append({
            "id": placement.pk, "parent": placement.parent_id, "kind": placement.kind, "name": placement.name,
            "hidden": placement.hidden, "system": placement.system,
            "owner": placement.owner, "group": placement.group, "mode": placement.mode,
            "access": placement.access_mode, "state": placement.state_mode,
            "item": None if item is None else {
                "id": item.pk, "slug": item.slug, "name": item.name, "format": item.format,
                "size": item.size if item.size is not None else (len(item.body.encode()) if item.body else None),
                "used": item.placements.count(),
            },
        })
    return {"rows": rows}


def formats():
    return [
        {"name": found.name, "title": found.title, "extension": found.extension, "markup": found.markup}
        for found in FileFormat.objects.order_by("name")
    ]


# ---- операции -------------------------------------------------------------------------------------------------------

@transaction.atomic
def new_folder(volume, parent_id, name):
    parent = folder_of(volume, parent_id)
    name = clean_name(name)
    check_free(volume, parent, name)
    depth_ok(parent)
    return Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.FOLDER, name=name)


@transaction.atomic
def new_file(volume, parent_id, typed, format_name=""):
    """Новый пустой файл: создаются объект и его размещение. Возвращает размещение."""
    parent = folder_of(volume, parent_id)
    title, found = split_file_name(typed, format_name)
    item = Item(slug=unique_slug(title), name=title, format=found.name if found else "")
    filename = item.default_filename
    check_free(volume, parent, filename)
    item.save()
    return Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.ITEM, item=item, name=filename)


@transaction.atomic
def new_item(typed, format_name="", slug="", volume=None, parent_id=None):
    """Новый пустой объект сам по себе (в библиотеке); если дан том, он сразу кладётся туда. Возвращает объект."""
    title, found = split_file_name(typed, format_name)
    slug = slug.strip()
    if slug:
        if Item.objects.filter(slug=slug).exists():
            raise FileManagerError("Объект с таким слагом уже есть.")
        item = Item(slug=slug, name=title, format=found.name if found else "")
        try:
            item.clean_fields(exclude=["name"])
        except ValidationError as error:
            raise FileManagerError(" ".join(error.message_dict.get("slug", error.messages)))
    else:
        item = Item(slug=unique_slug(title), name=title, format=found.name if found else "")
    if volume is not None:
        parent = folder_of(volume, parent_id)
        check_free(volume, parent, item.default_filename)
    item.save()
    if volume is not None:
        Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.ITEM, item=item, name=item.default_filename)
    return item


@transaction.atomic
def link(volume, parent_id, item_id, name=""):
    """Положить в папку уже существующий объект."""
    parent = folder_of(volume, parent_id)
    item = Item.objects.filter(pk=item_id).first()
    if item is None:
        raise FileManagerError("Такого объекта нет.")
    filename = clean_name(name) if name else item.default_filename
    check_free(volume, parent, filename)
    return Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.ITEM, item=item, name=filename)


def rename(volume, placement_id, name):
    placement = Placement.objects.filter(pk=placement_id, volume=volume).first()
    if placement is None:
        raise FileManagerError("Этого элемента нет.")
    name = clean_name(name)
    check_free(volume, placement.parent, name, ignore=placement.pk)
    placement.name = name
    placement.save(update_fields=["name"])
    return placement


@transaction.atomic
def delete(volume, ids):
    """Убрать размещения (папка уходит со всем внутри). Объекты остаются в библиотеке."""
    found = list(Placement.objects.filter(pk__in=ids, volume=volume))
    if not found:
        raise FileManagerError("Нечего удалять.")
    for placement in found:
        placement.delete()
    return len(found)


@transaction.atomic
def move(volume, ids, parent_id):
    parent = folder_of(volume, parent_id)
    moving = list(Placement.objects.filter(pk__in=ids, volume=volume))
    for placement in moving:
        if parent is not None and (parent.pk == placement.pk or _inside(parent, placement)):
            raise FileManagerError(f"Папку «{placement.name}» нельзя переместить в саму себя.")
        check_free(volume, parent, placement.name, ignore=placement.pk)
        depth_ok(parent)
    for placement in moving:
        placement.parent = parent
        placement.save(update_fields=["parent"])
    return len(moving)


def _inside(node, ancestor):
    seen = set()
    while node is not None and node.pk not in seen:
        if node.pk == ancestor.pk:
            return True
        seen.add(node.pk)
        node = node.parent
    return False


def copy_name(volume, parent, name):
    """«report.txt» занято -> «report - копия.txt», затем «report - копия (2).txt»."""
    stem, extension = posixpath.splitext(name)
    candidate, number = name, 1
    while siblings(volume, parent).filter(name=candidate).exists():
        candidate = f"{stem} - копия{'' if number == 1 else f' ({number})'}{extension}"
        number += 1
    return candidate


@transaction.atomic
def copy(volume, ids, parent_id):
    """Копия размещений (папка копируется со всем внутри); те же объекты, без дубликатов содержимого."""
    parent = folder_of(volume, parent_id)
    count = 0

    def clone(placement, target):
        nonlocal count
        fields = {name: getattr(placement, name) for name in ("kind", "item", "hidden", "system", "access_mode", "access", "state_mode", "state")}
        made = Placement.objects.create(volume=volume, parent=target, name=copy_name(volume, target, placement.name), **fields)
        count += 1
        for child in placement.children.all():
            clone(child, made)

    for placement in Placement.objects.filter(pk__in=ids, volume=volume).select_related("item"):
        if parent is not None and (parent.pk == placement.pk or _inside(parent, placement)):
            raise FileManagerError(f"Папку «{placement.name}» нельзя скопировать в саму себя.")
        depth_ok(parent)
        clone(placement, parent)
    return count


def set_rights(volume, placement_id, owner="", group="", mode=""):
    """Владелец, группа и режим размещения (пусто: права не заданы, открыто всем)."""
    placement = Placement.objects.filter(pk=placement_id, volume=volume).first()
    if placement is None:
        raise FileManagerError("Этого элемента нет.")
    placement.owner, placement.group, placement.mode = (owner or "").strip(), (group or "").strip(), (mode or "").strip()
    try:
        placement.full_clean(exclude=("name", "item", "parent", "volume", "access", "state"))
    except ValidationError as error:
        raise FileManagerError("; ".join(message for messages in error.message_dict.values() for message in messages))
    placement.save(update_fields=["owner", "group", "mode"])
    return placement


def set_flags(volume, placement_id, **flags):
    placement = Placement.objects.filter(pk=placement_id, volume=volume).first()
    if placement is None:
        raise FileManagerError("Этого элемента нет.")
    changed = []
    for name in ("hidden", "system"):
        if name in flags:
            setattr(placement, name, bool(flags[name]))
            changed.append(name)
    placement.save(update_fields=changed)
    return placement


@transaction.atomic
def apply_template(volume, template):
    """Создать в томе папки шаблона файловой структуры (None: пустой том). Возвращает сколько папок создано."""
    if template is None:
        return 0
    made = {}
    for path in template.paths():
        parent_path, _, name = path.rpartition("/")
        made[path] = Placement.objects.create(
            volume=volume, parent=made.get(parent_path), kind=Placement.Kind.FOLDER, name=name, system=template.system,
        )
    return len(made)


PLACEMENT_FIELDS = ("kind", "name", "item", "owner", "group", "mode", "hidden", "access_mode", "access", "state_mode", "state", "system")


@transaction.atomic
def copy_volume(volume, slug, name="", label=""):
    """Новый том с тем же деревом: те же папки и размещения тех же объектов (содержимое не дублируется), права и слои как были."""
    copy = Volume.objects.create(slug=slug, name=name, label=label, access=volume.access)
    made = {}
    rows = list(volume.placements.order_by("pk"))
    pending = rows
    while pending:                                     # родитель создаётся раньше детей, в каком бы порядке ни лежали строки
        left = []
        for row in pending:
            if row.parent_id is not None and row.parent_id not in made:
                left.append(row)
                continue
            made[row.pk] = Placement.objects.create(
                volume=copy, parent=made.get(row.parent_id), **{field: getattr(row, field) for field in PLACEMENT_FIELDS},
            )
        if len(left) == len(pending):
            break                                      # петля в дереве: оставшееся без родителя не копируется
        pending = left
    return copy


ITEM_FIELDS = ("name", "format", "body", "asset", "url", "scene", "message", "access", "state", "size", "meta",
               "world_created_at", "world_updated_at", "world_creator")


@transaction.atomic
def detach(placement, user=None):
    """Своя копия объекта для одного места: новый объект с тем же содержимым, ключами, подписями и членами архива, размещение
    переходит на него. Правки копии больше не трогают остальные места (и наоборот)."""
    original = placement.item
    if original is None:
        raise FileManagerError("Здесь лежит папка, а не объект.")
    copy = Item.objects.create(
        slug=unique_slug(original.slug), created_by=user, updated_by=user, **{field: getattr(original, field) for field in ITEM_FIELDS},
    )
    for link in original.keys.all():
        copy.keys.create(key=link.key)
    for link in original.signatures.all():
        copy.signatures.create(key=link.key, valid=link.valid, date=link.date)
    for member in original.members.all():
        copy.members.create(path=member.path, item=member.item)
    placement.item = copy
    placement.save(update_fields=["item"])
    return copy


def holders(item):
    """Что не даёт удалить объект: архивы, где он член, и объекты, куда он вложен ключом или подписью. [(вид, название)]."""
    found = [("архив", f"{member.archive.name} → {member.path}") for member in item.in_archives.select_related("archive")]
    found += [("вложен как ключ", link.item.name) for link in item.embedded_in.select_related("item")]
    found += [("подпись", link.item.name) for link in item.signed.select_related("item")]
    return found


@transaction.atomic
def delete_item(item):
    """Удалить объект вместе с его размещениями. Объект, который держат архивы, ключи или подписи, не удаляется."""
    held = holders(item)
    if held:
        raise FileManagerError("Объект нужен: " + "; ".join(f"{kind} {name}" for kind, name in held) + ".")
    count = item.placements.count()
    item.placements.all().delete()
    item.delete()
    return count


# ---- файл со своим текстом -------------------------------------------------------------------------------------------

@transaction.atomic
def new_text_file(volume, parent_id, name, content=""):
    """Файл со своим текстом (без объекта): декорация и фон. Формат определится по расширению имени."""
    parent = folder_of(volume, parent_id)
    name = clean_name(name)
    check_free(volume, parent, name)
    depth_ok(parent)
    return Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.FILE, name=name, content=content)


def set_text(volume, placement_id, content):
    placement = Placement.objects.filter(pk=placement_id, volume=volume, kind=Placement.Kind.FILE).first()
    if placement is None:
        raise FileManagerError("Это не файл со своим текстом.")
    placement.content = content
    placement.save(update_fields=["content"])
    return placement


@transaction.atomic
def to_item(placement, user=None):
    """Файл со своим текстом становится объектом: текст, условие и слои переезжают в объект, место ссылается на него.
    Нужно, когда файл понадобился в нескольких местах, с историей, ключами или подписями."""
    if placement.kind != Placement.Kind.FILE:
        raise FileManagerError("Это не файл со своим текстом.")
    stem, extension = posixpath.splitext(placement.name)
    found = format_by_extension(extension) if extension and stem else None
    item = Item.objects.create(
        slug=unique_slug(placement.name), name=stem if found else placement.name, format=found.name if found else "",
        body=placement.content, access=placement.access if placement.access_mode != Placement.Mode.NONE else {},
        state=placement.state if placement.state_mode != Placement.Mode.NONE else "", created_by=user, updated_by=user,
    )
    placement.kind, placement.item, placement.content = Placement.Kind.ITEM, item, ""
    placement.access, placement.state = {}, ""
    placement.access_mode = placement.state_mode = Placement.Mode.INHERIT
    placement.save()
    return item


def text_blockers(item):
    """Почему объект нельзя превратить в свой текст места: [причина]."""
    reasons = []
    if item.placements.count() > 1:
        reasons.append("лежит в нескольких местах")
    if item.in_archives.exists():
        reasons.append("входит в архив")
    if item.members.exists():
        reasons.append("это архив")
    if item.keys.exists() or item.signatures.exists():
        reasons.append("у него вложенные ключи или подписи")
    if item.embedded_in.exists() or item.signed.exists() or item.format == "key":
        reasons.append("это ключ")
    if item.asset_id or item.url or item.scene_id or item.message_id:
        reasons.append("его содержимое не текст")
    if item.mail_attachments.exists() or item.net_nodes.exists():
        reasons.append("на него ссылаются письма или сеть")
    if item.player_files.exists():
        reasons.append("у игроков есть его копии")
    return reasons


@transaction.atomic
def to_text(placement):
    """Объект, который лежит только здесь и ни с чем не связан, становится своим текстом места. История объекта пропадает."""
    item = placement.item
    if placement.kind != Placement.Kind.ITEM or item is None:
        raise FileManagerError("Здесь лежит не объект.")
    reasons = text_blockers(item)
    if reasons:
        raise FileManagerError("Нельзя: объект " + ", ".join(reasons) + ".")
    if not placement.name:
        placement.name = item.default_filename
    if placement.access_mode == Placement.Mode.INHERIT:
        placement.access = item.access
    if placement.state_mode == Placement.Mode.INHERIT:
        placement.state = item.state
    placement.kind, placement.item, placement.content = Placement.Kind.FILE, None, item.body
    placement.save()
    item.delete()
    return placement
