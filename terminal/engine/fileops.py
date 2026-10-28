"""mv и cp: перенос и копирование файлов и папок в слое игрока.

База не меняется, меняется слой игрока (filesystem/machine_view.py): mv переносит файл на новый путь, cp добавляет копию с тем же
прогрессом по слоям. Перезаписывать существующее нельзя: сначала del.
"""
import posixpath

from filesystem.trash import in_trash
from terminal.engine import trash
from terminal.engine.filesystem import VirtualFilesystem


def target_for(fs, source, dest):
    """Куда ляжет source, если назвали dest: существующая папка принимает файл под его именем."""
    if fs.is_directory(dest) and dest != source:
        return posixpath.join(dest, posixpath.basename(source))
    return dest


def check(context, fs, source, target, move, recursive):
    """Текст ошибки или None."""
    if not fs.exists(source):
        return "No such file or directory"
    if in_trash(source):
        return "in the trash, use rcvr"
    if in_trash(target):
        return "to the trash, use del"
    if fs.is_directory(source) and not (move or recursive):
        return "omitting directory (use -r)"
    if source == target:
        return "source and destination are the same"
    if target.startswith(source.rstrip("/") + "/"):
        return "cannot copy a directory into itself"
    if fs.exists(target):
        return f"'{target}' exists, delete it first"
    parent = posixpath.dirname(target) or "/"
    if parent not in ("/", context.home) and not fs.is_directory(parent):
        return f"'{parent}': No such file or directory"
    if move and trash.protection(context, source, None):
        return "Operation not permitted"
    return None


def apply(context, source, target, move):
    """Перенести или скопировать source (файл или папку со всем внутри) в target. Возвращает число файлов."""
    view = context.view
    count = view.move(source, target) if move else view.copy(source, target)
    context.invalidate()
    return count
