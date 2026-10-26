from filesystem.size import DIRECTORY_SIZE, file_size, human_size
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult


class BaseCommand:
    name = ""

    def execute(self, context, args: list[str]) -> CommandResult:
        raise NotImplementedError


class PwdCommand(BaseCommand):
    name = "pwd"

    def execute(self, context, args):
        if args:
            return CommandResult("pwd: too many arguments", 2)

        return CommandResult(context.cwd)


class LsCommand(BaseCommand):
    """ls [-a] [-l] [-h] [путь]: список; -l с размерами в байтах, -lh в привычных K и M."""

    name = "ls"

    def execute(self, context, args):
        flags = set()
        paths = []

        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                unknown = set(arg[1:]) - set("alh")
                if unknown:
                    return CommandResult(f"ls: unsupported option: -{sorted(unknown)[0]}", 2)
                flags |= set(arg[1:])
            else:
                paths.append(arg)

        if len(paths) > 1:
            return CommandResult("ls: too many paths", 2)

        path = context.resolve_path(paths[0]) if paths else context.cwd
        fs = VirtualFilesystem(context)

        if not fs.exists(path):
            return CommandResult(
                f"ls: cannot access '{path}': No such file or directory",
                2,
            )

        if not fs.is_directory(path):
            file = fs.get_file(path)
            name = file.path.rsplit("/", 1)[-1]
            return CommandResult(self._long([(file_size(file.machine_file), name)], "h" in flags) if "l" in flags else name)

        try:
            entries = fs.list_directory(path)
        except NotADirectoryError:
            return CommandResult(
                f"ls: '{path}': Not a directory",
                2,
            )

        names = [entry["name"] + ("/" if entry["is_directory"] else "")
                 for entry in entries]

        if "l" in flags:
            rows = [(self._size(fs, path, entry), name) for entry, name in zip(entries, names)]
            if "a" in flags:
                rows = [(DIRECTORY_SIZE, "./"), (DIRECTORY_SIZE, "../")] + rows
            return CommandResult(self._long(rows, "h" in flags))

        if "a" in flags:
            names = [".", ".."] + names

        return CommandResult("  ".join(names))

    @staticmethod
    def _size(fs, directory, entry):
        """Размер строки списка: у файла его собственный, у папки 4096."""
        if entry["is_directory"]:
            return DIRECTORY_SIZE
        file = fs.get_file(directory.rstrip("/") + "/" + entry["name"])
        return file_size(file.machine_file) if file else DIRECTORY_SIZE

    @staticmethod
    def _long(rows, human):
        """Строки «размер имя», размеры выровнены по правому краю."""
        shown = [(human_size(size) if human else str(size), name) for size, name in rows]
        width = max((len(size) for size, _ in shown), default=0)
        return "\n".join(f"{size:>{width}}  {name}" for size, name in shown)


class CdCommand(BaseCommand):
    name = "cd"

    def execute(self, context, args):
        if len(args) > 1:
            return CommandResult("cd: too many arguments", 2)

        target = args[0] if args else "/home"
        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)

        if not fs.exists(path):
            return CommandResult(
                f"cd: {target}: No such file or directory",
                1,
            )

        if not fs.is_directory(path):
            return CommandResult(
                f"cd: {target}: Not a directory",
                1,
            )

        context.cwd = path
        return CommandResult()


class ClearCommand(BaseCommand):
    name = "clear"

    def execute(self, context, args):
        if args:
            return CommandResult("clear: too many arguments", 2)

        return CommandResult(clear=True)
