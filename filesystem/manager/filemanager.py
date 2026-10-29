"""Операции файлового менеджера над томом: то, что автор делает кнопками «как в проводнике».

Всё работает с размещениями (Placement): файл в томе это строка дерева, а объект (Item) живёт отдельно и может лежать в
нескольких местах. Ошибки это FileManagerError с готовым текстом для автора.
"""
import posixpath

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from filesystem.models import FileFormat, Item, Placement
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
