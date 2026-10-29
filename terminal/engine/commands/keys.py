"""kex: достать ключ из байтов файла. Игрок находит блок ключа (txtx, blk, вьювер raw) и называет его смещение."""
from filesystem import keystore
from filesystem.content.rawview import keys
from filesystem.models import KEY_FORMAT, Item
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.rawinfo import raw_of
from terminal.engine.result import CommandResult
from terminal.scenes.shell import extract_scene

WINDOW = 16          # блок может начинаться чуть правее названного смещения: txtx склеивает его с предыдущими печатными байтами


def parse_offset(text):
    """Смещение: десятичное или 0x...; None, если это не число."""
    try:
        value = int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return None
    return value if value >= 0 else None


def find_block(data, offset):
    """(начало блока, слаг) в пределах WINDOW байт от offset, или None."""
    marker = keys.BEGIN.encode()
    span = data[offset:offset + WINDOW + len(marker)]
    at = span.find(marker)
    if at < 0 or at > WINDOW:
        return None
    slug = keys.parse(data, offset + at)
    return (offset + at, slug) if slug else None


class KexCommand(BaseCommand):
    """kex <файл> <смещение>: если с этого места в файле (каким его видит игрок сейчас) начинается блок ключа, ключ
    попадает в папку секретов записи. Пока файл закрыт слоем, по смещению шум, и ничего не находится."""

    name = "kex"
    usage = "usage: kex file offset"

    def execute(self, context, args):
        if len(args) != 2:
            return CommandResult(self.usage, 2)

        target = args[0]
        offset = parse_offset(args[1])
        if offset is None:
            return CommandResult(f"kex: invalid offset: {args[1]}", 2)

        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)
        if not fs.exists(path):
            return CommandResult(f"kex: cannot open '{target}': No such file or directory", 2)
        if fs.is_directory(path):
            return CommandResult(f"kex: {target}: Is a directory", 1)

        entry = fs.get_file(path)
        data = raw_of(context, entry).data
        found = find_block(data, offset) if offset < len(data) else None
        key = Item.objects.filter(slug=found[1], format=KEY_FORMAT).first() if found is not None else None
        known = key is not None
        scene = extract_scene(entry.path, offset, found is not None, known)

        if not known:
            return CommandResult(f"kex: {target}: no key at 0x{offset:x}", 1, scene=scene)

        saved, fresh = keystore.put(context.view, context.machine, context.profile.login, key)
        context.invalidate()
        line = f"extracted to {saved}" if fresh else f"already in {saved}"
        return CommandResult(f"kex: {target}: key {found[1]} {line}", 0, scene=scene)
