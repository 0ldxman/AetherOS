"""mv и cp: перенос и копирование файлов в сессии игрока (что и как, в terminal/engine/fileops.py)."""
from terminal.engine import fileops
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.commands.trash import _flags
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult


class _Transfer(BaseCommand):
    move = False
    flags = set()

    def execute(self, context, args):
        flags, operands = _flags(args)
        unknown = flags - self.flags
        if unknown:
            return CommandResult(f"{self.name}: unsupported option: -{sorted(unknown)[0]}\n{self.usage}", 2)
        if len(operands) < 2:
            return CommandResult(self.usage, 2)

        recursive = bool({"r", "R"} & flags)
        *sources, dest_arg = operands
        dest = context.resolve_path(dest_arg)
        fs = VirtualFilesystem(context)
        if len(sources) > 1 and not fs.is_directory(dest):
            return CommandResult(f"{self.name}: target '{dest_arg}' is not a directory", 1)

        lines, failed = [], False
        for operand in sources:
            source = context.resolve_path(operand)
            fs = VirtualFilesystem(context)                    # прежние операции уже изменили сессию
            target = fileops.target_for(fs, source, dest)
            error = fileops.check(context, fs, source, target, self.move, recursive)
            if error:
                lines.append(f"{self.name}: cannot {self.verb} '{operand}': {error}")
                failed = True
                continue
            fileops.apply(context, source, target, self.move)
            lines.append(f"{self.name}: {source} -> {target}")

        return CommandResult("\n".join(lines), 1 if failed else 0)


class Mv(_Transfer):
    name = "mv"
    verb = "move"
    move = True
    flags = set()
    usage = "usage: mv source... destination"


class Cp(_Transfer):
    name = "cp"
    verb = "copy"
    flags = {"r", "R"}
    usage = "usage: cp [-r] source... destination"
