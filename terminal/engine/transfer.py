"""Перенос файла между двумя сессиями (xfer): файл одной машины появляется в сессии другой.

Файл не копируется в базе как новая строка MachineFile: в сессии получателя появляется запись SessionFile, которая указывает
на файл отправителя и несёт его прогресс по слоям. Так же в сессию попадают доставленные файлы (вложения писем).
"""
import posixpath

from filesystem.models import SessionFile
from terminal.engine.context import DEFAULT_CWD
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

    state = entry.session_file.state if entry.session_file else ""
    return place_file(dest, entry.machine_file, state, dest_path, posixpath.basename(entry.path))


def place_file(dest, machine_file, state, dest_path, name):
    """Положить файл machine_file в сессию dest по пути dest_path (папка: под именем name) с прогрессом по слоям state.

    Возвращает (путь у получателя, None) или (None, текст ошибки в духе scp)."""
    dest_fs = VirtualFilesystem(dest)
    target = dest_path

    if dest_fs.is_directory(target):
        target = posixpath.join(target, name)

    parent = posixpath.dirname(target) or "/"
    if parent not in ("/", DEFAULT_CWD) and not dest_fs.is_directory(parent):
        return None, f"{dest_path}: No such file or directory"

    if dest_fs.is_directory(target):
        return None, f"{dest_path}: Is a directory"

    row = SessionFile.objects.filter(session=dest.session, path=target).first()

    # запись сессии прячет «нетронутый» файл машины: если копируют файл этой же машины, оригинал остаётся на месте
    if machine_file.machine_id == dest.machine.pk and not SessionFile.objects.filter(
        session=dest.session, file=machine_file
    ).exists():
        SessionFile.objects.create(session=dest.session, file=machine_file, path=machine_file.path)

    if row is None:
        SessionFile.objects.create(session=dest.session, file=machine_file, path=target, state=state)
    else:
        row.file = machine_file
        row.state = state
        row.deleted_at = None
        row.save()

    return target, None

