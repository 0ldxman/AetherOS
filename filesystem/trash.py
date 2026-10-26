"""Корзина сессии: что значит «файл в корзине» и как он исчезает насовсем.

Удалённый файл не пропадает: его запись SessionFile переезжает в /trash (origin_path помнит, откуда, trashed_at когда, purge_at
когда он удалится насовсем). Полное удаление не новый механизм: запись становится обычным надгробием (deleted_at), и
файл машины не появляется на старом месте. Файл, пришедший с другой машины (nget, xfer, вложение), надгробия не требует,
его запись просто удаляется.
"""
from django.utils import timezone

from filesystem.models import SessionFile

TRASH_DIR = "/trash"


def in_trash(path):
    return path == TRASH_DIR or path.startswith(TRASH_DIR + "/")


def trashed_rows(session):
    """Живые записи сессии, лежащие в корзине."""
    return SessionFile.objects.filter(session=session, purge_at__isnull=False, deleted_at__isnull=True).select_related("file")


def purge_row(row, machine_id):
    """Удалить файл из корзины насовсем."""
    if row.file.machine_id == machine_id:
        row.deleted_at = timezone.now()
        row.origin_path, row.trashed_at, row.purge_at = "", None, None
        row.save(update_fields=["deleted_at", "origin_path", "trashed_at", "purge_at"])
    else:
        row.delete()


def purge_expired(session=None):
    """Удалить насовсем всё, у чего вышел срок (у одной сессии или у всех). Возвращает сколько файлов."""
    rows = SessionFile.objects.filter(purge_at__lte=timezone.now(), deleted_at__isnull=True)
    if session is not None:
        rows = rows.filter(session=session)

    count = 0
    for row in rows.select_related("file", "session__profile"):
        purge_row(row, row.session.profile.machine_id)
        count += 1
    return count


def empty_trash(session):
    """Очистить корзину сессии. Возвращает сколько файлов."""
    machine_id = session.profile.machine_id
    rows = list(trashed_rows(session))
    for row in rows:
        purge_row(row, machine_id)
    return len(rows)
