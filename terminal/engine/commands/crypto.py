from filesystem import archives
from terminal.engine.commands.layered import LayerCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult


class WardCommand(LayerCommand):
    """ward <файл> <пароль>: снять шифрование (слой encrypted). Архивы он не открывает: у них свой пароль (pak pass)."""

    name = "ward"
    layer = "encrypted"
    done = "decrypted"
    absent = "not encrypted"

    def execute(self, context, args):
        if args:
            entry = VirtualFilesystem(context).get_file(context.resolve_path(args[0]))
            if entry is not None and archives.is_archive(entry.machine_file):
                return CommandResult(f"{self.name}: {args[0]}: no valid data found", 1)        # как gpg на чужом файле
        return super().execute(context, args)


class EncCommand(LayerCommand):
    """enc <файл>: раскодировать содержимое (слой base64)."""

    name = "enc"
    layer = "base64"
    done = "decoded"
    absent = "not base64"
