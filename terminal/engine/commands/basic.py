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
    name = "ls"

    def execute(self, context, args):
        show_all = False
        paths = []

        for arg in args:
            if arg == "-a":
                show_all = True
            elif arg == "-la" or arg == "-al":
                show_all = True
            elif arg.startswith("-"):
                return CommandResult(
                    f"ls: unsupported option: {arg}",
                    2,
                )
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
            return CommandResult(file.path.rsplit("/", 1)[-1])

        try:
            entries = fs.list_directory(path)
        except NotADirectoryError:
            return CommandResult(
                f"ls: '{path}': Not a directory",
                2,
            )

        names = [entry["name"] + ("/" if entry["is_directory"] else "")
                 for entry in entries]

        if show_all:
            names = [".", ".."] + names

        return CommandResult("  ".join(names))


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