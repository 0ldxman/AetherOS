"""Корзина игрока: что значит «файл в корзине» и как он исчезает насовсем.

Удалённый файл не пропадает: он переезжает в корзину учётки (место trash, по умолчанию {home}/.trash) в мире, а его запись помнит, откуда (origin_path), когда удалён
(trashed_at) и когда исчезнет насовсем (purge_at). Полное удаление это просто удаление этой записи: на старом месте файла уже нет,
там осталось надгробие (или файл игрока ушёл без следа).
"""
from django.utils import timezone

from filesystem.machine_view import MachineView
from filesystem.models import FileChange

def in_trash(path, trash_dir):
    return path == trash_dir or path.startswith(trash_dir + "/")


def trashed(view, trash_dir):
    """Файлы корзины записи: записи вида машины, у которых есть срок."""
    return [
        entry for path, entry in sorted(view.entries.items())
        if in_trash(path, trash_dir) and not entry.is_dir and entry.player is not None and entry.player.purge_at is not None
    ]


def purge_expired(user=None):
    """Удалить насовсем всё, у чего вышел срок (в экземпляре игрока или везде). Возвращает сколько файлов."""
    from filesystem.machine_view.view import world_of

    rows = FileChange.objects.filter(purge_at__lte=timezone.now(), deleted_at__isnull=True)
    if user is not None:
        rows = rows.filter(sandbox=world_of(user))
    count = rows.count()
    rows.delete()
    if count:
        MachineView.generation += 1                 # собранные за запрос виды устарели
    return count


def to_trash(view, trash_dir, path):
    """Перенести файл или папку path в корзину записи под тем же именем (занято: name.1, name.2).
    Возвращает [(путь в корзине, прежний путь)] для каждого файла."""
    import posixpath

    from django.conf import settings

    files = [entry for entry in view.under(path) if not entry.is_dir]
    name = posixpath.basename(path)
    candidate, number = name, 0
    while view.exists(posixpath.join(trash_dir, candidate)):
        number += 1
        candidate = f"{name}.{number}"
    target = posixpath.join(trash_dir, candidate)
    view.move(path, target)
    now = timezone.now()
    moved = []
    for entry in files:
        new_path = target + entry.path[len(path):]
        row = view.get(new_path).player
        row.origin_path, row.trashed_at, row.purge_at = entry.path, now, now + settings.TRASH_TTL
        row.save(update_fields=["origin_path", "trashed_at", "purge_at"])
        moved.append((new_path, entry.path))
    view.invalidate()
    return moved


def empty_trash(view, trash_dir):
    """Очистить корзину записи. Возвращает сколько файлов."""
    from filesystem import fileevents

    found = trashed(view, trash_dir)
    for entry in found:
        item = entry.item.slug if entry.item is not None else ""
        view.remove(entry.path)
        fileevents.purged(view, entry.path, item)
    return len(found)
