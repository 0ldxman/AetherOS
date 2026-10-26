import re
import posixpath

from filesystem.content import resolve_content
from filesystem.size import file_size
from filesystem.states.attempt import top_answer
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult
from terminal.scenes import ftyp_scene, open_scene


# Что ftyp говорит о файле, на который не ответил ни один слой.
PLAIN_FILE = "data"
DIRECTORY = "directory"


class FtypCommand(BaseCommand):
    """ftyp <файл>: что это за файл. Отвечает верхний слой файла, у которого
    есть ответ на ftyp (текст автора файла или умолчание слоя)."""

    name = "ftyp"

    def execute(self, context, args):
        if not args:
            return CommandResult("ftyp: missing file operand", 2)

        if len(args) > 1:
            return CommandResult("ftyp: too many arguments", 2)

        target = args[0]
        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)

        if not fs.exists(path):
            return CommandResult(
                f"ftyp: cannot open '{target}': No such file or directory",
                2,
            )

        if fs.is_directory(path):
            return CommandResult(f"{target}: {DIRECTORY}")

        entry = fs.get_file(path)
        session_file = entry.session_file

        text = top_answer(
            entry.machine_file.state,
            session_file.state if session_file else "",
            self.name,
            path=entry.path,
            name=posixpath.basename(entry.path),
        )

        return CommandResult(f"{target}: {text if text is not None else PLAIN_FILE}", scene=ftyp_scene(entry.path))



class CntCommand(BaseCommand):
    """cnt <файл>: открыть содержимое файла.

    Сначала проверяется ответ верхнего слоя cnt.
    Если такого ответа нет и блокирующих слоёв больше нет,
    открывается MachineFile.url.
    """

    name = "cnt"

    def execute(self, context, args):
        if not args:
            return CommandResult("cnt: missing file operand", 2)

        if len(args) > 1:
            return CommandResult("cnt: too many arguments", 2)

        target = args[0]
        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)

        if not fs.exists(path):
            return CommandResult(
                f"cnt: cannot open '{target}': No such file or directory",
                2,
            )

        if fs.is_directory(path):
            return CommandResult(f"cnt: {target}: Is a directory", 1)

        entry = fs.get_file(path)
        machine_file = entry.machine_file
        session_file = entry.session_file
        name = posixpath.basename(entry.path)

        content = resolve_content(machine_file, session_file, entry.path, name)

        if content.error == "locked":
            return CommandResult(f"cnt: {target}: content is locked", 1, scene=open_scene(entry.path, "access"))

        if content.error == "empty":
            return CommandResult(f"cnt: {target}: no content", 1, scene=open_scene(entry.path, "content"))

        if content.error:
            return CommandResult(f"cnt: {target}: bad content path", 1)

        url = content.url

        return CommandResult(
            f"cnt: {target}: opened ({file_size(machine_file)} bytes)",
            0,
            {
                "id": "cnt-" + re.sub(r"\W+", "-", entry.path).strip("-"),
                "title": name,
                "url": url,
            },
            scene=open_scene(entry.path, "opened"),
        )
