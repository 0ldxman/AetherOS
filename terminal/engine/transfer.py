"""Перенос файла между двумя сессиями (xfer): файл одной машины появляется в слое игрока на другой.

Файл не копируется в базе: в слое игрока у получателя появляется запись, которая указывает на тот же объект и несёт прогресс по
слоям (а у файла игрока без объекта собственное содержимое). Так же в слой попадают доставленные файлы (вложения писем).
"""
import posixpath

from terminal.engine.filesystem import VirtualFilesystem


def copy_file(source, source_path, dest, dest_path):
    """Скопировать файл source_path из сессии source в dest_path сессии dest (оба это TerminalContext).

    Возвращает (путь у получателя, None) или (None, текст ошибки в духе scp)."""
    source_fs = VirtualFilesystem(source)
    entry = source_fs.get_file(source_path)

    if entry is None and not source_fs.exists(source_path):
        return None, f"{source_path}: No such file or directory"

    if entry is None or source_fs.is_directory(source_path):
        return None, f"{source_path}: not a regular file"
    source.require(source_path, "r")

    return place_entry(dest, entry, dest_path, posixpath.basename(entry.path))


def _target(dest, dest_path, name):
    """(путь у получателя, ошибка в духе scp)."""
    dest_fs = VirtualFilesystem(dest)
    target = dest_path

    if dest_fs.is_directory(target):
        target = posixpath.join(target, name)

    parent = posixpath.dirname(target) or "/"
    if parent not in ("/", dest.home) and not dest_fs.is_directory(parent):
        return None, f"{dest_path}: No such file or directory"

    if dest_fs.is_directory(target):
        return None, f"{dest_path}: Is a directory"

    return target, None


def place_entry(dest, entry, dest_path, name):
    """Положить файл вида машины entry в слой игрока у dest по пути dest_path (папка: под именем name), с прогрессом по слоям.

    Возвращает (путь у получателя, None) или (None, текст ошибки в духе scp)."""
    target, error = _target(dest, dest_path, name)
    if error:
        return None, error

    view = dest.view
    if entry.item is not None:
        view.put_item(target, entry.item, entry.progress, entry.text_override)
    elif entry.own_data is not None:
        view.put_data(target, entry.own_data, entry.progress)
    else:
        view.put_text(target, entry.own_text or "", entry.progress)
    dest.invalidate()
    return target, None


def place_item(dest, item, state, dest_path, name):
    """Положить объект item в слой игрока у dest по пути dest_path с прогрессом по слоям state (nget, вложение письма)."""
    target, error = _target(dest, dest_path, name)
    if error:
        return None, error

    dest.view.put_item(target, item, state)
    dest.invalidate()
    return target, None


def hop_seconds(size):
    """Сколько секунд файл size байт идёт по одному прыжку: больше файл, дольше (от 1 до 8 секунд)."""
    return min(8.0, 1.0 + size / 1024 / 300)
