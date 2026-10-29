"""Правки машины для автора: файловая система машины редактируется как единое дерево, а изменения ложатся в её собственный
том отличий (docs/storage-spec.md, «отличия машины»).

Том отличий монтируется на ту же точку, что и изменяемый слой, и лежит над ним. Он создаётся лениво, при первом изменении.
  перекрыть   копия объекта в томе отличий под тем же путём (общий объект не трогается);
  скрыть      надгробие в томе отличий (файл нижнего слоя исчезает из вида машины);
  восстановить  убрать надгробие;  сбросить  убрать перекрытие (вернётся файл нижнего слоя).
"""
import posixpath

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count

from filesystem.manager.filemanager import FileManagerError, check_free, clean_name, split_file_name, unique_slug
from filesystem.machine_view import MachineView
from filesystem.models import Item, ItemKey, ItemSignature, Placement, Volume
from machines.models import MachineMount


def is_private(machine, mount):
    """Том смонтирован только на эту машину (его правка не заденет других)."""
    return mount.mode == "local" and not MachineMount.objects.filter(volume_id=mount.volume_id).exclude(machine=machine).exists()


def rel_inner(point, path):
    """Путь на машине -> путь внутри тома отличий, смонтированного на точку."""
    path = "/" + path.strip("/")
    if point == "/":
        return path.strip("/")
    return path[len(point):].strip("/") if path == point or path.startswith(point + "/") else path.strip("/")


def point_for(view, path):
    """Точка, в чьей власти путь: самая глубокая из тех, что его покрывают (для нового файла в папке path)."""
    covering = [layer.point for layer in view.layers if layer.inner_path(path) is not None]
    return max(covering, key=lambda point: point.count("/") if point != "/" else 0, default="/")


def overlay_for(machine, point, create=True):
    """(монтирование, том) отличий машины на этой точке; создаётся при первом обращении."""
    mounts = list(MachineMount.objects.filter(machine=machine, mount_path=point).select_related("volume").order_by("order", "id"))
    top = mounts[-1] if mounts else None
    if top is not None and top.volume_path == "" and is_private(machine, top):
        return top, top.volume
    if not create:
        return None, None
    base = f"{machine.label}-own"
    slug, number = base, 1
    while Volume.objects.filter(slug=slug).exists():
        number += 1
        slug = f"{base}-{number}"
    volume = Volume.objects.create(slug=slug, label=f"Отличия {machine.label}")
    mount = MachineMount.objects.create(machine=machine, volume=volume, mount_path=point, order=(top.order + 1) if top else 0)
    return mount, volume


def find_placement(volume, rel):
    """Размещение тома по пути внутри него или None."""
    parent = None
    node = None
    for name in [part for part in rel.split("/") if part]:
        node = Placement.objects.filter(volume=volume, parent=parent, name=name).first()
        if node is None:
            return None
        parent = node
    return node


FOLDER_FIELDS = ("hidden", "system", "owner", "group", "mode", "access_mode", "access", "state_mode", "state")


def ensure_folders(volume, rel_dir, view=None, point="/"):
    """Папки до rel_dir создаются, если их нет. Возвращает последнюю (None: корень).

    Новая папка отличий закрывает папку нижнего слоя на машине, поэтому берёт её свойства (права, условия, флаги): view и точка
    монтирования нужны, чтобы найти ту папку."""
    parent = None
    walked = []
    for name in [part for part in rel_dir.split("/") if part]:
        walked.append(name)
        node = Placement.objects.filter(volume=volume, parent=parent, name=name).first()
        if node is None:
            fields = {}
            if view is not None:
                below = view.get(("" if point == "/" else point) + "/" + "/".join(walked))
                if below is not None and below.placement is not None:
                    fields = {key: getattr(below.placement, key) for key in FOLDER_FIELDS}
            node = Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.FOLDER, name=name, **fields)
        elif node.kind != Placement.Kind.FOLDER:
            raise FileManagerError(f"«{name}» в томе отличий не папка.")
        parent = node
    return parent


def clone_item(item, machine):
    """Копия объекта для этой машины: содержимое, доступ, слои, ключи и подписи."""
    copy = Item.objects.create(
        slug=unique_slug(f"{item.slug}-{machine.label}"), name=item.name, format=item.format, body=item.body, asset=item.asset,
        url=item.url, scene=item.scene, message=item.message, access=item.access, state=item.state, size=item.size, meta=item.meta,
        world_created_at=item.world_created_at, world_updated_at=item.world_updated_at, world_creator=item.world_creator,
    )
    for row in item.keys.all():
        ItemKey.objects.create(item=copy, key=row.key)
    for row in item.signatures.all():
        ItemSignature.objects.create(item=copy, key=row.key, valid=row.valid, date=row.date)
    return copy


def _lower_has(view, machine, point, overlay_mount, path):
    """Есть ли путь в слоях ниже тома отличий на этой точке."""
    for layer in view.layers:
        if layer.point == point and layer.mount.order < overlay_mount.order and layer.mount.pk != overlay_mount.pk:
            if path in view.layer_paths(layer):
                return True
    return False


def _entry(view, path):
    entry = view.get(path)
    if entry is None:
        raise FileManagerError("Такого пути нет.")
    if entry.via is not None:
        raise FileManagerError("Это сетевой диск: файлы правятся на хосте.")
    return entry


@transaction.atomic
def override(machine, path):
    """Подготовить файл к правке на этой машине. Возвращает объект, который открывается в редакторе."""
    view = MachineView(machine, None)
    entry = _entry(view, path)
    if entry.is_dir or entry.item is None:
        raise FileManagerError("Перекрыть можно только файл.")
    mount = entry.layer.mount
    if mount.volume_path == "" and is_private(machine, mount):
        return entry.item                                              # файл уже из тома отличий: правится на месте
    overlay_mount, volume = overlay_for(machine, entry.layer.point)
    rel = rel_inner(entry.layer.point, path)
    parent = ensure_folders(volume, posixpath.dirname(rel), view, entry.layer.point)
    existing = Placement.objects.filter(volume=volume, parent=parent, name=posixpath.basename(rel)).first()
    if existing is not None:
        if existing.kind == Placement.Kind.WHITEOUT:
            existing.delete()
        else:
            return existing.item
    copy = clone_item(entry.item, machine)
    source = entry.placement
    Placement.objects.create(
        volume=volume, parent=parent, kind=Placement.Kind.ITEM, item=copy, name=posixpath.basename(rel),
        hidden=bool(source and source.hidden), system=bool(source and source.system),
        owner=source.owner if source else "", group=source.group if source else "", mode=source.mode if source else "",
        access_mode=source.access_mode if source else Placement.Mode.INHERIT, access=source.access if source else {},
        state_mode=source.state_mode if source else Placement.Mode.INHERIT, state=source.state if source else "",
    )
    return copy


@transaction.atomic
def set_rights(machine, path, owner="", group="", mode=""):
    """Права файла или папки на этой машине: меняются в её собственном томе (файл общего образа перекрывается копией)."""
    view = MachineView(machine, None)
    entry = _entry(view, path)
    owner, group, mode = (owner or "").strip(), (group or "").strip(), (mode or "").strip()
    if entry.is_dir:
        point = entry.layer.point if entry.layer is not None else point_for(view, path)
        _, volume = overlay_for(machine, point)
        rel = rel_inner(point, path)
        if not rel:
            raise FileManagerError("Права точки монтирования задаёт сам том.")
        placement = ensure_folders(volume, rel, view, point)
    else:
        override(machine, path)
        _, volume = overlay_for(machine, entry.layer.point)
        placement = find_placement(volume, rel_inner(entry.layer.point, path))
    placement.owner, placement.group, placement.mode = owner, group, mode
    try:
        placement.full_clean(exclude=("name", "item", "parent", "volume", "access", "state"))
    except ValidationError as error:
        raise FileManagerError("; ".join(message for messages in error.message_dict.values() for message in messages))
    placement.save(update_fields=["owner", "group", "mode"])
    return placement


@transaction.atomic
def delete(machine, path):
    """Убрать файл или папку из вида машины: свой файл удаляется, файл нижнего слоя скрывается надгробием."""
    view = MachineView(machine, None)
    entry = _entry(view, path)
    point = entry.layer.point if entry.layer is not None else point_for(view, path)
    overlay_mount, volume = overlay_for(machine, point)
    rel = rel_inner(point, path)
    own = find_placement(volume, rel)
    if own is not None and own.kind != Placement.Kind.WHITEOUT:
        own.delete()
    came_from_below = entry.layer is None or entry.layer.mount.pk != overlay_mount.pk
    if came_from_below or _lower_has(view, machine, point, overlay_mount, path):
        if find_placement(volume, rel) is None:
            parent = ensure_folders(volume, posixpath.dirname(rel))
            Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.WHITEOUT, name=posixpath.basename(rel))
    return True


@transaction.atomic
def restore(machine, path):
    """Вернуть скрытое: убрать надгробие из тома отличий."""
    view = MachineView(machine, None)
    for layer in view.layers:
        found = view.layer_paths_of_kind(layer, Placement.Kind.WHITEOUT).get("/" + path.strip("/"))
        if found is not None:
            if not is_private(machine, layer.mount):
                raise FileManagerError(f"Надгробие лежит в общем томе «{layer.mount.volume.slug}»: уберите его в самом томе.")
            found.delete()
            return True
    raise FileManagerError("Это не скрыто.")


@transaction.atomic
def reset(machine, path):
    """Сбросить перекрытие: убрать файл или папку из тома отличий, вернётся то, что лежит ниже."""
    view = MachineView(machine, None)
    entry = _entry(view, path)
    point = entry.layer.point if entry.layer is not None else point_for(view, path)
    overlay_mount, volume = overlay_for(machine, point, create=False)
    found = find_placement(volume, rel_inner(point, path)) if volume is not None else None
    if found is None or found.kind == Placement.Kind.WHITEOUT:
        raise FileManagerError("На этой машине этот путь не менялся.")
    found.delete()
    return True


def _target(machine, parent_path):
    view = MachineView(machine, None)
    parent_path = "/" + parent_path.strip("/")
    if parent_path != "/" and not view.is_directory(parent_path):
        raise FileManagerError("Такой папки нет.")
    point = point_for(view, parent_path)
    return view, point, parent_path


@transaction.atomic
def new_folder(machine, parent_path, name):
    name = clean_name(name)
    view, point, parent_path = _target(machine, parent_path)
    if view.exists(posixpath.join(parent_path, name)):
        raise FileManagerError(f"«{name}» уже есть в этой папке.")
    overlay_mount, volume = overlay_for(machine, point)
    parent = ensure_folders(volume, rel_inner(point, parent_path))
    return Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.FOLDER, name=name)


@transaction.atomic
def new_file(machine, parent_path, typed, format_name=""):
    title, found = split_file_name(typed, format_name)
    item = Item(slug=unique_slug(title), name=title, format=found.name if found else "")
    filename = item.default_filename
    view, point, parent_path = _target(machine, parent_path)
    if view.exists(posixpath.join(parent_path, filename)):
        raise FileManagerError(f"«{filename}» уже есть в этой папке.")
    overlay_mount, volume = overlay_for(machine, point)
    parent = ensure_folders(volume, rel_inner(point, parent_path))
    item.save()
    return Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.ITEM, item=item, name=filename)


@transaction.atomic
def rename(machine, path, name):
    """Переименовать: свой элемент переименовывается, файл нижнего слоя скрывается и появляется под новым именем."""
    name = clean_name(name)
    view = MachineView(machine, None)
    entry = _entry(view, path)
    parent_path = posixpath.dirname("/" + path.strip("/")) or "/"
    if view.exists(posixpath.join(parent_path, name)):
        raise FileManagerError(f"«{name}» уже есть в этой папке.")
    point = entry.layer.point if entry.layer is not None else point_for(view, path)
    overlay_mount, volume = overlay_for(machine, point, create=False)
    own = find_placement(volume, rel_inner(point, path)) if volume is not None and entry.layer is not None and entry.layer.mount.pk == overlay_mount.pk else None
    if own is not None:
        own.name = name
        own.save(update_fields=["name"])
        return own
    if entry.is_dir or entry.item is None:
        raise FileManagerError("Папку образа переименовать нельзя: создайте новую и перенесите файлы.")
    delete(machine, path)
    overlay_mount, volume = overlay_for(machine, point)
    parent = ensure_folders(volume, rel_inner(point, parent_path))
    return Placement.objects.create(volume=volume, parent=parent, kind=Placement.Kind.ITEM, item=entry.item, name=name)


# ---- данные менеджера -----------------------------------------------------------------------------------------------

def _items_info(items):
    counts = dict(Item.objects.filter(pk__in=[item.pk for item in items]).annotate(n=Count("placements")).values_list("pk", "n"))
    return {
        item.pk: {
            "id": item.pk, "slug": item.slug, "name": item.name, "format": item.format, "used": counts.get(item.pk, 0),
            "size": item.size if item.size is not None else (len(item.body.encode()) if item.body else None),
        }
        for item in items
    }


def machine_data(machine):
    """Собранное дерево машины для менеджера: файлы, папки и (красным) то, что скрыто надгробиями."""
    view = MachineView(machine, None)
    layers = [layer for layer in view.layers if not layer.remote]
    by_point, below_paths, whiteouts = {}, {}, {}
    for layer in layers:
        by_point.setdefault(layer.point, []).append(layer)
        below_paths[layer.mount.pk] = view.layer_paths(layer)
        whiteouts[layer.mount.pk] = view.layer_paths_of_kind(layer, Placement.Kind.WHITEOUT)
    info = _items_info([entry.item for entry in view.entries.values() if entry.item is not None])

    rows = []
    for path, entry in sorted(view.entries.items()):
        if path == "/":
            continue
        row = {"path": path, "name": entry.name, "kind": "dir" if entry.is_dir else "file", "volume": "", "mark": "", "private": False,
               "hidden": entry.hidden, "system": entry.system, "item": None, "owner": entry.owner, "group": entry.group, "mode": entry.mode}
        if entry.via is not None:
            row.update(volume=f"{entry.via.mount.host.label}:{entry.via.mount.host_path}", mark="remote")
        elif entry.layer is not None:
            stack = sorted(by_point[entry.layer.point], key=lambda layer: layer.mount.order)
            below = [layer for layer in stack if layer.mount.order < entry.layer.mount.order]
            row["volume"] = entry.layer.mount.volume.slug
            row["private"] = is_private(machine, entry.layer.mount)
            if not entry.is_dir:
                if not below:
                    row["mark"] = "base" if len(stack) > 1 else ""
                elif any(path in below_paths[layer.mount.pk] for layer in below):
                    row["mark"] = "override"
                else:
                    row["mark"] = "added"
        if entry.item is not None:
            row["item"] = info[entry.item.pk]
        rows.append(row)

    deleted = []
    for layer in layers:
        stack = [other for other in by_point[layer.point] if other.mount.order < layer.mount.order]
        for path, placement in whiteouts[layer.mount.pk].items():
            if any(path in below_paths[other.mount.pk] for other in stack):
                deleted.append({
                    "path": path, "name": posixpath.basename(path), "kind": "deleted", "volume": layer.mount.volume.slug,
                    "private": is_private(machine, layer.mount), "mark": "deleted", "hidden": False, "system": False, "item": None,
                })
    return {"rows": rows + sorted(deleted, key=lambda row: row["path"])}
