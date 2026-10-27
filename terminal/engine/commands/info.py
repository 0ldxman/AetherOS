import re
import posixpath

from filesystem.content import resolve_content
from filesystem.rawview import detect
from filesystem.models import SessionFile
from filesystem.states.attempt import top_answer
from filesystem.unlock import fire_file_event
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.rawinfo import raw_of, size_of
from terminal.engine.report import hook_report
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

        if text is None:
            found = detect(raw_of(context, entry).data)            # как file: по началу самих байтов (у вырезки это единственный след)
            text = found.title if found else PLAIN_FILE

        return CommandResult(f"{target}: {text}", scene=ftyp_scene(entry.path))



class CntCommand(BaseCommand):
    """cnt <файл>: открыть содержимое файла.

    Сначала проверяется ответ верхнего слоя cnt.
    Если такого ответа нет и блокирующих слоёв больше нет,
    открывается MachineFile.url.
    """

    name = "cnt"

    def execute(self, context, args):
        raw_view = "-r" in args
        args = [arg for arg in args if arg != "-r"]

        if not args:
            return CommandResult("cnt: missing file operand", 2)

        if len(args) > 1:
            return CommandResult("cnt: too many arguments", 2)

        request = context.request
        if request is not None and request.user.is_authenticated:
            from machines import bridge

            if bridge.terminal_id(request) != bridge.desktop_id(request):
                return CommandResult("cnt: no display: the desktop is on another machine", 1)    # окно открылось бы не на той машине

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

        if raw_view:
            # cnt -r: сырые байты файла во вьювере raw; слои и хуки read не трогаются (это не «открыть», а «заглянуть внутрь»)
            from filesystem.views import raw_url

            return CommandResult(
                f"cnt: {target}: opened in the raw viewer ({size_of(context, entry)} bytes)",
                0,
                {"id": "raw-" + re.sub(r"\W+", "-", entry.path).strip("-"), "title": f"{name} [raw]", "url": raw_url(entry.path)},
                scene=open_scene(entry.path, "opened"),
            )

        # хуки on read верхнего слоя: могут сказать что-то или открыть окно (open), а слой остаётся на месте
        lines, effects = [], None
        if machine_file.state.strip() or (session_file and session_file.state):
            if session_file is None:
                session_file, _ = SessionFile.objects.get_or_create(
                    session=context.session, path=entry.path, defaults={"file": machine_file}
                )
            lines, effects = hook_report([fire_file_event(session_file, "read", entry.path)])

        if effects and any(effect["op"] == "open" for effect in effects):
            text = "\n".join([f"cnt: {target}: opened ({size_of(context, entry)} bytes)", *lines])
            return CommandResult(text, 0, scene=open_scene(entry.path, "opened"), effects=effects)

        content = resolve_content(machine_file, session_file, entry.path, name)

        def result(text, code, stage, window=None):
            return CommandResult("\n".join([text, *lines]), code, window, scene=open_scene(entry.path, stage), effects=effects)

        if content.error == "locked":
            return result(f"cnt: {target}: content is locked", 1, "access")

        if content.error == "empty":
            return result(f"cnt: {target}: no content", 1, "content")

        if content.error:
            return CommandResult("\n".join([f"cnt: {target}: bad content path", *lines]), 1, effects=effects)

        window = {"id": "cnt-" + re.sub(r"\W+", "-", entry.path).strip("-"), "title": name, "url": content.url}
        return result(f"cnt: {target}: opened ({size_of(context, entry)} bytes)", 0, "opened", window)
