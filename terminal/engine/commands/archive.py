"""pak: работа с архивами файловой системы (файл с расширением, под путём которого лежат другие файлы машины).

    pak l <архив>                            список членов
    pak x <архив> [член...] [-d папка]       распаковать всё или выбранное (по умолчанию в папку рядом без расширения)
    pak pass <архив> <пароль>                снять пароль архива (слой encrypted; у обычных файлов это ward)

Пока на архиве есть слой (пароль, повреждение...), список и распаковка отказывают, как настоящий unzip.
"""
import posixpath

from filesystem import archives
from filesystem.models import SessionFile
from filesystem.states.attempt import peek_top, top_answer
from filesystem.trash import in_trash
from terminal.engine import trash
from terminal.engine.commands.layered import LayerCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.rawinfo import keys_of, viewer_of
from terminal.engine.result import CommandResult
from terminal.scenes import pak_extract_scene, pak_list_scene
from filesystem.size import file_size

USAGE = "usage: pak l archive\n       pak x archive [member...] [-d dir]\n       pak pass archive password"

# что говорит архиватор, когда его читать нельзя из-за слоя
BLOCKED = {
    "encrypted": "password required",
    "damaged": "Unexpected EOF in archive",
    "corrupted": "Unexpected EOF in archive",
}
NOT_ARCHIVE = "This does not look like an archive"


class PakCommand(LayerCommand):
    name = "pak"
    layer = "encrypted"
    done = "unlocked"
    absent = "not password protected"

    def execute(self, context, args):
        if not args or args[0] not in ("l", "x", "pass"):
            return CommandResult(USAGE, 2)
        mode, rest = args[0], args[1:]
        if mode == "pass":
            return self.password(context, rest)
        return self.read(context, mode, rest)

    # --- общая часть ---

    def open(self, context, target):
        """(запись архива, ошибка): ошибка это готовый CommandResult."""
        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)
        if not fs.exists(path):
            return None, CommandResult(f"pak: cannot open '{target}': No such file or directory", 2)
        if fs.is_directory(path):
            return None, CommandResult(f"pak: {target}: Is a directory", 1)
        entry = fs.get_file(path)
        if not archives.is_archive(entry.machine_file):
            return None, CommandResult(f"pak: {target}: not an archive", 1)
        return entry, None

    def blocked(self, entry, target):
        """Отказ, если на архиве есть слой (верхний отвечает сам), иначе None."""
        state = entry.session_file.state if entry.session_file else ""
        top = peek_top(entry.machine_file.state, state)
        if top is None:
            return None
        text = top_answer(entry.machine_file.state, state, self.name, path=entry.path, name=posixpath.basename(entry.path), only_top=True)
        return CommandResult(f"pak: {target}: {text if text is not None else BLOCKED.get(top.state.name, NOT_ARCHIVE)}", 1)

    # --- pass ---

    def password(self, context, rest):
        if len(rest) != 2:
            return CommandResult(USAGE, 2)
        target, password = rest
        entry, error = self.open(context, target)
        if error:
            return error
        state = entry.session_file.state if entry.session_file else ""
        top = peek_top(entry.machine_file.state, state)
        if top is not None and top.state.name != self.layer:
            return self.blocked(entry, target)
        return self.unlock(context, target, [password], self.layer)

    def fail_for(self, context, entry, target, wrong, values):
        return f"pak: {target}: incorrect password"

    # --- l, x ---

    def read(self, context, mode, rest):
        if mode == "l":
            if len(rest) != 1:
                return CommandResult(USAGE, 2)
            names, dest = [], None
        else:
            names, dest, error = [], None, None
            items = list(rest)
            target = items.pop(0) if items else None
            while items:
                item = items.pop(0)
                if item == "-d":
                    if not items:
                        return CommandResult("pak: option -d requires an argument", 2)
                    dest = items.pop(0)
                else:
                    names.append(item.strip("/"))
            if target is None:
                return CommandResult(USAGE, 2)
            rest = [target]

        target = rest[0]
        entry, error = self.open(context, target)
        if error:
            return error
        refusal = self.blocked(entry, target)
        if refusal:
            return refusal

        found = archives.members(entry.machine_file)
        if mode == "l":
            return self.listing(context, entry, found)
        return self.extract(context, entry, found, names, dest)

    def listing(self, context, entry, found):
        """Дерево членов, как tree: папки первыми, у файлов размер справа."""
        keys, viewer = keys_of(context), viewer_of(context)
        tree = {}
        total = 0
        for name, item in found:
            size = file_size(item, "", keys, viewer)
            total += size
            node = tree
            *folders, leaf = name.split("/")
            for folder in folders:
                node = node.setdefault(folder, {})
            node[leaf] = size

        rows = []

        def walk(node, prefix):
            names = sorted(node, key=lambda key: (not isinstance(node[key], dict), key.casefold()))
            for number, key in enumerate(names):
                last = number == len(names) - 1
                value = node[key]
                rows.append((f"{prefix}{'└── ' if last else '├── '}{key}{'/' if isinstance(value, dict) else ''}",
                             None if isinstance(value, dict) else value))
                if isinstance(value, dict):
                    walk(value, prefix + ("    " if last else "│   "))

        walk(tree, "")
        width = max([len(text) for text, _ in rows] + [len(posixpath.basename(entry.path))])
        sizes = max([len(str(size)) for _, size in rows if size is not None] + [1])
        lines = [posixpath.basename(entry.path)]
        lines += [text if size is None else f"{text:<{width}}  {size:>{sizes}}" for text, size in rows]
        lines.append("")
        lines.append(f"{len(found)} file{'s' if len(found) != 1 else ''}, {total} bytes")
        return CommandResult("\n".join(lines), 0, scene=pak_list_scene(entry.path, len(found)))

    def extract(self, context, entry, found, names, dest):
        fs = VirtualFilesystem(context)
        chosen = found
        if names:
            chosen = [(name, item) for name, item in found if any(name == want or name.startswith(want + "/") for want in names)]
            for want in names:
                if not any(name == want or name.startswith(want + "/") for name, _ in found):
                    return CommandResult(f"pak: {want}: Not found in archive", 1)

        base = posixpath.basename(entry.path)
        folder = context.resolve_path(dest) if dest else posixpath.join(posixpath.dirname(entry.path), posixpath.splitext(base)[0])
        if in_trash(folder):
            return CommandResult(f"pak: {folder}: to the trash, use del", 1)
        if fs.exists(folder) and not fs.is_directory(folder):
            return CommandResult(f"pak: '{folder}' exists and is not a directory", 1)
        for name, _ in chosen:
            if fs.exists(posixpath.join(folder, name)):
                return CommandResult(f"pak: '{posixpath.join(folder, name)}' exists, delete it first", 1)

        for name, item in chosen:
            target = posixpath.join(folder, name)
            trash._claim(context.session, target)
            SessionFile.objects.create(session=context.session, file=item, path=target)

        lines = [f"x {name}" for name, _ in chosen]
        lines.append(f"pak: extracted {len(chosen)} file{'s' if len(chosen) != 1 else ''} to {folder}")
        return CommandResult("\n".join(lines), 0, scene=pak_extract_scene(entry.path, [name for name, _ in chosen]))
