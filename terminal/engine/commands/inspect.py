"""txtx: читаемые строки из сырых байтов файла, как strings. Ничего не снимает: это подсказка для cvt, pak и других."""
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.rawinfo import raw_of
from terminal.engine.result import CommandResult
from terminal.scenes import strings_scene

MIN_LENGTH = 4
MAX_LINES = 200


def printable_runs(data, minimum=MIN_LENGTH):
    """[(смещение, строка)] для подряд идущих печатных ASCII-символов не короче minimum."""
    runs, start = [], None
    for index, byte in enumerate(data + b"\0"):
        if 32 <= byte < 127 or byte == 9:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= minimum:
                runs.append((start, data[start:index].decode("ascii")))
            start = None
    return runs


class TxtxCommand(BaseCommand):
    name = "txtx"
    usage = "usage: txtx file"

    def execute(self, context, args):
        if len(args) != 1:
            return CommandResult(self.usage, 2)

        target = args[0]
        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)
        if not fs.exists(path):
            return CommandResult(f"txtx: cannot open '{target}': No such file or directory", 2)
        if fs.is_directory(path):
            return CommandResult(f"txtx: {target}: Is a directory", 1)

        entry = fs.get_file(path)
        data = raw_of(context, entry).data
        runs = printable_runs(data)
        lines = [f"0x{offset:06x}  {text}" for offset, text in runs[:MAX_LINES]]
        if len(runs) > MAX_LINES:
            lines.append(f"... {len(runs) - MAX_LINES} more")
        return CommandResult("\n".join(lines), 0, scene=strings_scene(entry.path, len(data)))
