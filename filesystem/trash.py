"""Корзина игрока: что значит «файл в корзине» и как он исчезает насовсем.

Удалённый файл не пропадает: он переезжает в корзину записи (место trash, по умолчанию {home}/.trash) слоя игрока, а его запись помнит, откуда (origin_path), когда удалён
(trashed_at) и когда исчезнет насовсем (purge_at). Полное удаление это просто удаление этой записи: на старом месте файла уже нет,
там осталось надгробие (или файл игрока ушёл без следа).
"""
from django.utils import timezone

from filesystem.models import PlayerFile

def in_trash(path, trash_dir):
    return path == trash_dir or path.startswith(trash_dir + "/")


def trashed(view, trash_dir):
    """Файлы корзины записи: записи вида машины, у которых есть срок."""
    return [
        entry for path, entry in sorted(view.entries.items())
        if in_trash(path, trash_dir) and not entry.is_dir and entry.player is not None and entry.player.purge_at is not None
    ]


def purge_expired(user=None):
    """Удалить насовсем всё, у чего вышел срок (у одного игрока или у всех). Возвращает сколько файлов."""
    rows = PlayerFile.objects.filter(purge_at__lte=timezone.now(), deleted_at__isnull=True)
    if user is not None:
        rows = rows.filter(user=user)
    count = rows.count()
    rows.delete()
    return count


def empty_trash(view, trash_dir):
    """Очистить корзину записи. Возвращает сколько файлов."""
    found = trashed(view, trash_dir)
    for entry in found:
        view.remove(entry.path)
    return len(found)
