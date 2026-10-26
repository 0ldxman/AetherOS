"""mv и cp: перенос и копирование файлов и папок внутри сессии игрока.

Файл машины не меняется, меняется запись сессии (SessionFile): mv сдвигает её путь, cp добавляет копию с тем же прогрессом
по слоям. Перезаписывать существующее нельзя: сначала del.
"""
import posixpath

from filesystem.models import SessionFile
from filesystem.trash import in_trash
from terminal.engine import trash
from terminal.engine.context import DEFAULT_CWD
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
    if parent not in ("/", DEFAULT_CWD) and not fs.is_directory(parent):
        return f"'{parent}': No such file or directory"
    if move and trash.protection(context, source, trash.under(fs._entries(), source)):
        return "Operation not permitted"
    return None


def apply(context, source, target, move):
    """Перенести или скопировать source (файл или папку со всем внутри) в target. Возвращает число файлов."""
    session = context.session
    fs = VirtualFilesystem(context)
    found = trash.under(fs._entries(), source)

    for entry in found:
        new_path = target + entry.path[len(source):]
        trash._claim(session, new_path)                                    # надгробие на пути уступает место
        row = entry.session_file

        if move:
            if row is None:
                SessionFile.objects.create(session=session, file=entry.machine_file, path=new_path)
            else:
                row.path = new_path
                row.save(update_fields=["path"])
            continue

        if row is None:
            # запись сессии прячет «нетронутый» файл машины: оригинал остаётся на месте своей записью
            SessionFile.objects.create(session=session, file=entry.machine_file, path=entry.path)
        SessionFile.objects.create(
            session=session, file=entry.machine_file, path=new_path, state=row.state if row else ""
        )

    return len(found)
