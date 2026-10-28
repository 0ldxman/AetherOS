"""Корзина игрока: что значит «файл в корзине» и как он исчезает насовсем.

Удалённый файл не пропадает: он переезжает в /trash слоя игрока, а его запись помнит, откуда (origin_path), когда удалён
(trashed_at) и когда исчезнет насовсем (purge_at). Полное удаление это просто удаление этой записи: на старом месте файла уже нет,
там осталось надгробие (или файл игрока ушёл без следа).
"""
from django.utils import timezone

from filesystem.models import PlayerFile

TRASH_DIR = "/trash"


def in_trash(path):
    return path == TRASH_DIR or path.startswith(TRASH_DIR + "/")


def trashed(view):
    """Файлы корзины игрока: записи вида машины, у которых есть срок."""
    return [
        entry for path, entry in sorted(view.entries.items())
        if in_trash(path) and not entry.is_dir and entry.player is not None and entry.player.purge_at is not None
    ]


def purge_expired(user=None):
    """Удалить насовсем всё, у чего вышел срок (у одного игрока или у всех). Возвращает сколько файлов."""
    rows = PlayerFile.objects.filter(purge_at__lte=timezone.now(), deleted_at__isnull=True)
    if user is not None:
        rows = rows.filter(user=user)
    count = rows.count()
    rows.delete()
    return count


def empty_trash(view):
    """Очистить корзину игрока. Возвращает сколько файлов."""
    found = trashed(view)
    for entry in found:
        view.remove(entry.path)
    return len(found)
