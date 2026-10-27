import posixpath

from filesystem.models import SessionFile
from filesystem.rawview.registry import format_for_extension
from filesystem.states.attempt import peek_top
from terminal.engine import fileops
from terminal.engine.commands.layered import LayerCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.hexdump import hexdump
from terminal.engine.rawinfo import raw_of, size_of
from terminal.engine.result import CommandResult
from terminal.scenes import block_scene, convert_scene, decode_scene, repair_scene

BLOCK = 512
MAX_BLOCKS = 4


class RprCommand(LayerCommand):
    """rpr <файл>: восстановить файл, снимает один слой damaged. Если под ним ещё один, сцена и ответ говорят, что нужна
    ещё одна починка."""

    name = "rpr"
    layer = "damaged"
    done = "repaired"
    absent = "nothing to repair"

    @staticmethod
    def _more(rest):
        return rest is not None and rest.state.name == "damaged"

    def scene_for(self, context, layer, entry, ok, rest, values):
        return repair_scene(entry.path, size_of(context, entry), ok, self._more(rest))

    def done_for(self, rest):
        return "repaired with errors, further repair required" if self._more(rest) else self.done


class BlkCommand(LayerCommand):
    """blk <файл> [skip] [count]: прочитать count блоков по 512 байт, начиная с skip, и показать их (hexdump), как dd.

    Если на файле слой shifted и названы оба числа, это ещё и попытка его снять."""

    name = "blk"
    layer = "shifted"
    done = "blocks read"
    absent = "nothing to read"

    def execute(self, context, args):
        if not args or len(args) > 3:
            return CommandResult("usage: blk file [skip] [count]", 2)

        try:
            skip = int(args[1]) if len(args) > 1 else 0
            count = int(args[2]) if len(args) > 2 else 1
        except ValueError:
            return CommandResult("blk: skip and count must be whole numbers", 2)
        if skip < 0 or count < 1:
            return CommandResult("blk: skip must be 0 or more and count 1 or more", 2)
        asked, count = count, min(count, MAX_BLOCKS)     # показываем не больше MAX_BLOCKS, снимать слой пробуем с названным

        target = args[0]
        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)
        if not fs.exists(path):
            return CommandResult(f"blk: cannot open '{target}': No such file or directory", 2)
        if fs.is_directory(path):
            return CommandResult(f"blk: {target}: Is a directory", 1)

        entry = fs.get_file(path)
        data = raw_of(context, entry).data
        chunk = data[skip * BLOCK:(skip + count) * BLOCK]
        whole, rest = divmod(len(chunk), BLOCK)
        records = f"{whole}+{1 if rest else 0} records"
        lines = [*hexdump(chunk, skip * BLOCK), f"{records} in", f"{records} out", f"{len(chunk)} bytes copied"]

        top = peek_top(entry.machine_file.state, entry.session_file.state if entry.session_file else "")
        if len(args) == 3 and top is not None and top.state.name == self.layer:
            result = self.unlock(context, target, [str(skip), str(asked)], self.layer)
            return CommandResult("\n".join([*lines, result.output]), result.exit_code, scene=result.scene, effects=result.effects)

        if not chunk:
            return CommandResult("\n".join(lines), 1, scene=block_scene(entry.path, 0))
        return CommandResult("\n".join(lines), 0, scene=block_scene(entry.path, whole + (1 if rest else 0)))


class CvtCommand(LayerCommand):
    """cvt <файл> <формат или кодировка>: прочитать файл как названный формат (слой disguised) или раскодировать
    из названной кодировки (слой binary). Неверное название не подсказывает правильное, но ошибка показывает, что на
    самом деле стоит в начале файла."""

    name = "cvt"
    layer = "disguised"
    done = "converted"
    absent = "nothing to convert"
    USAGE = "usage: cvt ext file out | cvt enc encoding file"

    def execute(self, context, args):
        if args and args[0] == "ext" and len(args) == 3:
            return self.convert_format(context, args[1], args[2])
        if args and args[0] == "enc" and len(args) == 3:
            return self.unlock(
                context, args[2], [args[1]], "binary", absent="nothing to decode",
                scene=lambda entry, ok, rest: decode_scene(entry.path, size_of(context, entry), args[1], ok),
            )
        return CommandResult(self.USAGE, 2)

    def convert_format(self, context, target, out):
        """cvt ext файл файл.pdf: копия под новым именем с прочитанным контейнером, исходник остаётся как был.
        cvt ext файл .pdf: тот же файл, расширение заменено."""
        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)
        base = posixpath.basename(out)
        in_place = base.startswith(".") and base.count(".") == 1       # назвали одно расширение
        ext = base.lower() if in_place else posixpath.splitext(base)[1]
        found = format_for_extension(ext) if ext else None
        name = found.name if found else ext.lstrip(".")
        if not name:
            return CommandResult(self.USAGE, 2)

        if not fs.exists(path) or fs.is_directory(path):
            return self.unlock(context, target, [name], "disguised")

        def scene(entry, ok, rest):
            return convert_scene(entry.path, size_of(context, entry), name, ok, None if in_place else destination)

        destination = context.resolve_path(posixpath.splitext(target)[0] + ext if in_place else out)
        problem = fileops.check(context, fs, path, destination, in_place, False)
        if problem:
            return CommandResult(f"cvt: {out}: {problem}", 1)

        def finish(entry, before):
            if in_place:
                fileops.apply(context, entry.path, destination, True)
                return f"  {entry.path} -> {destination}"
            fileops.apply(context, entry.path, destination, False)
            if entry.session_file is not None:
                entry.session_file.state = before                  # у исходника слой остаётся, снят он только с копии
                entry.session_file.save(update_fields=["state"])
            else:
                SessionFile.objects.filter(session=context.session, path=entry.path).update(state=before)
            return f"  {destination}"

        return self.unlock(context, target, [name], "disguised", finish=finish, scene=scene)

    def fail_for(self, context, entry, target, wrong, values):
        head = " ".join(f"{byte:02x}" for byte in raw_of(context, entry).data[:16])
        top = peek_top(entry.machine_file.state, entry.session_file.state if entry.session_file else "")
        verb = "decode" if top is not None and top.state.name == "binary" else "read"
        return f"{self.name}: {target}: cannot {verb} as {values[0]}\n  unexpected header: {head}"

