"""perm и own: права и владелец файла. Права меняет владелец (или root), владельца меняет запись с привилегией chown."""
import re

from filesystem import rights
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult

MODE = re.compile(r"^[0-7]{3}$")


def _files(context, command, operands):
    """([записи], ошибка): записи файлов по путям, ошибка это готовый CommandResult."""
    fs = VirtualFilesystem(context)
    found = []
    for operand in operands:
        path = context.resolve_path(operand)
        if not fs.exists(path):
            return None, CommandResult(f"{command}: cannot access '{operand}': No such file or directory", 1)
        if fs.is_directory(path):
            return None, CommandResult(f"{command}: {operand}: Is a directory", 1)
        found.append(fs.get_file(path))
    return found, None


class PermCommand(BaseCommand):
    """perm <права> <файл>...: права тремя цифрами (владелец, группа, остальные): 4 читать, 2 писать, 1 входить."""

    name = "perm"
    usage = "usage: perm mode file...   (mode: three digits, e.g. 640)"

    def execute(self, context, args):
        if len(args) < 2 or not MODE.match(args[0]):
            return CommandResult(self.usage, 2)
        files, error = _files(context, self.name, args[1:])
        if error:
            return error
        principal = context.principal
        for entry in files:
            owner, _, mode = rights.rights_of(context.view, entry)
            if not principal.root and (mode or owner) and principal.login != owner:
                raise rights.NotPermitted("owner")
        for entry in files:
            context.view.set_rights(entry.path, mode=args[0])
        context.invalidate()
        return CommandResult()


class OwnCommand(BaseCommand):
    """own <владелец>[:<группа>] <файл>...: передать файл. Нужна привилегия chown."""

    name = "own"
    usage = "usage: own owner[:group] file..."

    def execute(self, context, args):
        if len(args) < 2:
            return CommandResult(self.usage, 2)
        owner, _, group = args[0].partition(":")
        if not owner and not group:
            return CommandResult(self.usage, 2)
        context.need("chown")
        logins = set(context.machine.profiles.values_list("login", flat=True))
        if owner and owner not in logins:
            return CommandResult(f"{self.name}: invalid user: '{owner}'", 1)
        files, error = _files(context, self.name, args[1:])
        if error:
            return error
        fields = {key: value for key, value in (("owner", owner), ("group", group)) if value}
        for entry in files:
            context.view.set_rights(entry.path, **fields)
        context.invalidate()
        return CommandResult()
