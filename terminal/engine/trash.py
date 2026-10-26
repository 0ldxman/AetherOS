"""Корзина в терминале: перенос в /trash (del) и возврат (rcvr). Что такое «в корзине» и как файл исчезает насовсем,
в filesystem/trash.py.
"""
import posixpath
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from filesystem.models import ProtectedPath, SessionFile
from filesystem.states.stack import load_progress
from filesystem.trash import TRASH_DIR, in_trash, trashed_rows
from terminal.engine.filesystem import VirtualFilesystem


def under(entries, path):
    """Записи самого path и всего, что лежит внутри."""
    prefix = path.rstrip("/") + "/"
    return [entry for entry in entries.values() if entry.path == path or entry.path.startswith(prefix)]


def protection(context, path, found):
    """Почему path нельзя удалить: текст причины или None. Нельзя защищённый путь (и всё, что его содержит) и системный файл."""
    prefix = path.rstrip("/") + "/"
    machine = context.machine.pk
    for item in ProtectedPath.objects.filter(machine__isnull=True) | ProtectedPath.objects.filter(machine_id=machine):
        if item.path == path or item.path.startswith(prefix):
            return "Operation not permitted"
    if any(entry.machine_file.system for entry in found):
        return "Operation not permitted"
    return None


def _claim(session, path):
    """Освободить путь от надгробия (удалённого раньше файла), чтобы запись могла встать на него."""
    SessionFile.objects.filter(session=session, path=path, deleted_at__isnull=False).delete()


def trash(context, path):
    """Перенести файл или папку path в /trash под тем же именем (занято: name.1, name.2). Возвращает число файлов."""
    fs = VirtualFilesystem(context)
    found = under(fs._entries(), path)
    name = posixpath.basename(path)
    candidate, number = name, 0
    while fs.exists(posixpath.join(TRASH_DIR, candidate)):
        number += 1
        candidate = f"{name}.{number}"

    now = timezone.now()
    for entry in found:
        rest = entry.path[len(path):]
        target = posixpath.join(TRASH_DIR, candidate) + rest
        _claim(context.session, target)
        fields = {"path": target, "origin_path": entry.path, "trashed_at": now, "purge_at": now + settings.TRASH_TTL}
        if entry.session_file is not None:
            for key, value in fields.items():
                setattr(entry.session_file, key, value)
            entry.session_file.save()
        else:
            SessionFile.objects.create(session=context.session, file=entry.machine_file, **fields)
    return len(found)


def damage_layers(row, now):
    """Сколько слоёв damaged получит файл при возврате: минимум один, потом по слою за каждый шаг времени в корзине."""
    waited = now - row.trashed_at if row.trashed_at else timedelta(0)
    return min(settings.TRASH_DAMAGE_MAX, 1 + int(waited / settings.TRASH_DAMAGE_STEP))


def recover(context, path, dest=None):
    """Вернуть файл (или папку) из корзины. Возвращает (список итоговых путей, None) или (None, текст ошибки).

    Файл возвращается на прежнее место (или в dest) и получает слои damaged: чем дольше лежал, тем больше."""
    session = context.session
    prefix = path.rstrip("/") + "/"
    rows = [row for row in trashed_rows(session) if row.path == path or row.path.startswith(prefix)]
    if not rows:
        return None, "No such file or directory"

    folder = not any(row.path == path for row in rows)
    if folder and dest:
        return None, "a destination can only be given for a single file"

    fs = VirtualFilesystem(context)
    plan = []
    for row in rows:
        target = dest or row.origin_path
        if fs.exists(target):
            return None, f"{target}: File exists, give another path"
        plan.append((row, target))

    now = timezone.now()
    for row, target in plan:
        progress = load_progress(row.state, row.file.state)
        for _ in range(damage_layers(row, now)):
            progress.push("damaged")
        _claim(session, target)
        row.state = progress.dump()
        row.path = target
        row.origin_path, row.trashed_at, row.purge_at = "", None, None
        row.save()
    return [target for _, target in plan], None
