import posixpath

from filesystem.states.attempt import top_answer
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult

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

        return CommandResult(f"{target}: {text if text is not None else PLAIN_FILE}")
