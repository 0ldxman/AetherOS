"""Корзина в терминале: перенос в корзину записи (del) и возврат (rcvr). Что такое «в корзине» и как файл исчезает насовсем,
в filesystem/trash.py.
"""
import posixpath
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from filesystem.states.stack import load_progress
from filesystem.trash import trashed
from filesystem.unlock import fire_file_event
from terminal.engine.filesystem import VirtualFilesystem


def under(entries, path):
    """Записи самого path и всего, что лежит внутри."""
    prefix = path.rstrip("/") + "/"
    return [entry for entry in entries.values() if entry.path == path or entry.path.startswith(prefix)]


def protection(context, path, found):
    """Почему path нельзя удалить: текст причины или None. Нельзя то, что содержит системный файл или папку (защищённый путь)."""
    for entry in context.view.under(path):
        if entry.system:
            return "Operation not permitted"
    return None


def trash(context, path):
    """Перенести файл или папку path в корзину записи под тем же именем (занято: name.1, name.2).
    Возвращает [(путь в корзине, прежний путь)] для каждого файла."""
    fs = VirtualFilesystem(context)
    view = context.view
    files = [entry for entry in view.under(path) if not entry.is_dir]
    name = posixpath.basename(path)
    candidate, number = name, 0
    while fs.exists(posixpath.join(context.trash_dir, candidate)):
        number += 1
        candidate = f"{name}.{number}"

    target = posixpath.join(context.trash_dir, candidate)
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


def damage_layers(row, now):
    """Сколько слоёв damaged получит файл при возврате: минимум один, потом по слою за каждый шаг времени в корзине."""
    waited = now - row.trashed_at if row.trashed_at else timedelta(0)
    return min(settings.TRASH_DAMAGE_MAX, 1 + int(waited / settings.TRASH_DAMAGE_STEP))


def recover(context, path, dest=None):
    """Вернуть файл (или папку) из корзины. Возвращает ([(итоговый путь, итог хуков)], None) или (None, текст ошибки).

    Файл возвращается на прежнее место (или в dest) и получает слои damaged: чем дольше лежал, тем больше.
    Хуки restore автора файла берут верхний слой до порчи, их итог исполняет команда."""
    view = context.view
    prefix = path.rstrip("/") + "/"
    found = [entry for entry in trashed(view, context.trash_dir) if entry.path == path or entry.path.startswith(prefix)]
    if not found:
        return None, "No such file or directory"

    folder = not any(entry.path == path for entry in found)
    if folder and dest:
        return None, "a destination can only be given for a single file"

    fs = VirtualFilesystem(context)
    plan = []
    for entry in found:
        target = dest or entry.player.origin_path
        if fs.exists(target):
            return None, f"{target}: File exists, give another path"
        plan.append((entry, target))

    now = timezone.now()
    recovered = []
    for entry, target in plan:
        layers = damage_layers(entry.player, now)
        state, author = entry.progress, entry.state
        view.move(entry.path, target)

        fired = fire_file_event(view, target, "restore", target)          # хук автора видит файл ещё целым
        progress = load_progress(view.get(target).progress if fired is not None else state, author)
        for _ in range(layers):
            progress.push("damaged")
        view.set_progress(target, progress.dump())
        recovered.append((target, fired))
    return recovered, None
