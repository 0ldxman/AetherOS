"""Изменения мира на машине для автора: что игроки поменяли поверх базы (FileChange без песочницы), кто и когда, и откат —
убрать изменение, чтобы снова был виден файл из базы. Песочницы авторов здесь не видны."""
from filesystem.machine_view import MachineView
from filesystem.models import FileChange


def _rows(machine):
    """[(путь на машине, строка изменения)] по локальным томам машины, от мелких путей к глубоким."""
    view = MachineView(machine, None)
    found = []
    by_instance = {layer.instance.pk: layer for layer in view.layers if layer.instance is not None}
    for row in FileChange.objects.filter(sandbox__isnull=True, instance_id__in=by_instance).select_related("item", "changed_by"):
        path = by_instance[row.instance_id].machine_path(row.path)
        if path is not None:
            found.append((path, row))
    return sorted(found, key=lambda pair: (pair[0].count("/"), pair[0])), view


def changes(machine):
    """Изменения мира: [{path, kind, by, at, item}]. kind: deleted (удалён), trashed (в корзине), edited (правка файла из базы),
    added (новый файл игрока), progress (сняты слои)."""
    found, base = _rows(machine)
    result = []
    for path, row in found:
        under = base.get(path)
        if row.deleted_at is not None:
            kind = "deleted"
        elif row.trashed_at is not None:
            kind = "trashed"
        elif under is None:
            kind = "added"
        elif row.content is not None or row.data is not None or (row.item_id is not None and (under.item is None or under.item.pk != row.item_id)):
            kind = "edited"
        else:
            kind = "progress"
        result.append({"path": path, "kind": kind, "by": row.changed_by.get_username() if row.changed_by_id else "", "at": row.updated_at,
                       "item": row.item.name if row.item_id else ""})
    return result


def revert(machine, path=""):
    """Откатить изменения мира на пути (и под ним); пусто — все на машине. Возвращает сколько изменений убрано."""
    found, _ = _rows(machine)
    path = "/" + path.strip("/") if path else ""
    gone = [row.pk for where, row in found if not path or where == path or where.startswith(path.rstrip("/") + "/")]
    FileChange.objects.filter(pk__in=gone).delete()
    if gone:
        MachineView.generation += 1
    return len(gone)


def set_keep(machine, path, keep):
    """«Игрок не может удалить»: у размещения базы на этом пути. False — нет такого размещения."""
    entry = MachineView(machine, None).get(path)
    if entry is None or entry.placement is None:
        return False
    type(entry.placement).objects.filter(pk=entry.placement.pk).update(keep=bool(keep))
    MachineView.generation += 1
    return True
