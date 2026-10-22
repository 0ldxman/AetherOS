import posixpath

from filesystem.states.attempt import top_answer
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult

import re

from django.urls import get_script_prefix

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


class CntCommand(BaseCommand):
    """cnt <файл>: открыть содержимое файла в окне. Путь окна задаёт
    верхний слой строкой `cnt: apps/wiki/go/test` в описании файла."""

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
        session_file = entry.session_file
        name = posixpath.basename(entry.path)

        url_path = top_answer(
            entry.machine_file.state,
            session_file.state if session_file else "",
            self.name,
            path=entry.path,
            name=name,
            only_top=True,
        )

        if url_path is None:
            return CommandResult(f"cnt: {target}: no content", 1)

        url_path = url_path.strip()

        # Только внутренние пути сайта, без внешних адресов.
        if "://" in url_path or url_path.startswith("//") or "\\" in url_path:
            return CommandResult(f"cnt: {target}: bad content path", 1)

        url = get_script_prefix().rstrip("/") + "/" + url_path.lstrip("/")

        return CommandResult(
            f"cnt: {target}: opened",
            0,
            {
                "id": "cnt-" + re.sub(r"\W+", "-", entry.path).strip("-"),
                "title": name,
                "url": url,
            },
        )