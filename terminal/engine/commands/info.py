import posixpath

from filesystem.states.attempt import top_answer
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult

import re

from django.urls import get_script_prefix

from filesystem.states.compiler import compile_text
from filesystem.states.stack import build_stack, load_progress
from filesystem.states.registry import registry

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

        canonical_text = machine_file.state or ""
        raw_state = session_file.state if session_file else ""

        # Приоритет: ответ верхнего слоя cnt.
        url_path = top_answer(
            canonical_text,
            raw_state,
            self.name,
            path=entry.path,
            name=name,
            only_top=True,
        )

        if url_path is None:
            # Проверяем эффективный стек с учётом прогресса сессии.
            canonical = (
                compile_text(canonical_text, registry)
                if canonical_text.strip()
                else []
            )
            progress = load_progress(raw_state, canonical_text)
            stack = build_stack(canonical, progress, registry)

            if stack:
                return CommandResult(f"cnt: {target}: content is locked", 1)

            # Стек пуст — используем URL самого файла.
            url_path = machine_file.url

        if not url_path or not url_path.strip():
            return CommandResult(f"cnt: {target}: no content", 1)

        url_path = url_path.strip()

        # Разрешены только внутренние пути сайта.
        if (
            "://" in url_path
            or url_path.startswith("//")
            or "\\" in url_path
            or url_path.startswith("/")
        ):
            return CommandResult(f"cnt: {target}: bad content path", 1)

        url = get_script_prefix().rstrip("/") + "/" + url_path

        return CommandResult(
            f"cnt: {target}: opened",
            0,
            {
                "id": "cnt-" + re.sub(r"\W+", "-", entry.path).strip("-"),
                "title": name,
                "url": url,
            },
        )
