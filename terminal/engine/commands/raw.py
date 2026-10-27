import posixpath

from filesystem import slices
from filesystem.models import SessionFile
from filesystem.rawview.registry import format_for_extension
from filesystem.states.attempt import peek_top
from terminal.engine import fileops
from terminal.engine.commands.layered import LayerCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.commands.keys import parse_offset
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
    """blk -i <вход> -o <выход> skip=N [count=M] | start=A [end=B]: вырезать кусок файла в новый файл, как dd.

    Окно задаётся блоками по 512 байт (skip, count) или адресами байтов (start, end; end не входит). Без count и end
    вырезается всё до конца файла. Читаются те же байты, что показывают cnt -r и txtx: под шифром это шум.

    Если на файле слой shifted и окно начинается ровно на данных и не короче их, новый файл настоящий: слой снят с его
    копии. Любое другое окно даёт файл из тех байтов, что попали в окно. Исходный файл не меняется."""

    name = "blk"
    layer = "shifted"
    done = "copied"
    absent = "nothing to copy"
    usage = "usage: blk -i input -o output skip=N [count=M]\n       blk -i input -o output start=A [end=B]"
    KEYS = ("skip", "count", "start", "end")

    def parse(self, args):
        """Словарь с input, output, start, end (end None: до конца файла) или текст ошибки."""
        given, flags = {}, {}
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("-i", "-o"):
                if i + 1 >= len(args):
                    return f"blk: option {arg} requires an argument"
                flags[arg] = args[i + 1]
                i += 2
            elif "=" in arg and arg.split("=", 1)[0] in self.KEYS:
                key, value = arg.split("=", 1)
                number = parse_offset(value) if key in ("start", "end") else (int(value) if value.isdigit() else None)
                if number is None:
                    return f"blk: invalid {key}: {value}"
                given[key] = number
                i += 1
            else:
                return self.usage
        if "-i" not in flags or "-o" not in flags or not given:
            return self.usage
        if {"skip", "count"} & given.keys() and {"start", "end"} & given.keys():
            return "blk: use either skip/count or start/end, not both"
        if {"skip", "count"} & given.keys():
            skip = given.get("skip", 0)
            if given.get("count", 1) < 1:
                return "blk: count must be 1 or more"
            start = skip * BLOCK
            end = (skip + given["count"]) * BLOCK if "count" in given else None
        else:
            start, end = given.get("start", 0), given.get("end")
        if end is not None and end <= start:
            return "blk: end must be after start"
        return {"input": flags["-i"], "output": flags["-o"], "start": start, "end": end}

    def execute(self, context, args):
        opts = self.parse(args)
        if isinstance(opts, str):
            return CommandResult(opts, 2)

        target, out = opts["input"], opts["output"]
        path = context.resolve_path(target)
        destination = context.resolve_path(out)
        fs = VirtualFilesystem(context)
        if not fs.exists(path):
            return CommandResult(f"blk: cannot open '{target}': No such file or directory", 2)
        if fs.is_directory(path):
            return CommandResult(f"blk: {target}: Is a directory", 1)
        problem = fileops.check(context, fs, path, destination, False, False)
        if problem:
            return CommandResult(f"blk: {out}: {problem}", 1)

        entry = fs.get_file(path)
        raw = raw_of(context, entry)
        data, start, end = raw.data, opts["start"], opts["end"]
        if start >= len(data):
            return CommandResult(f"blk: {target}: start is beyond the end of the file ({len(data)} bytes)", 1)

        scanning = end is None
        end = min(len(data), end if end is not None else len(data))
        raw_state = entry.session_file.state if entry.session_file else ""
        top = peek_top(entry.machine_file.state, raw_state)
        real = (
            top is not None and top.state.name == self.layer
            and start == int(top.params["skip"]) * BLOCK and end >= len(data) - BLOCK
        )
        if real:
            end = len(data) - BLOCK                         # хвост шума за данными в файл не попадает

        length = end - start
        whole, rest = divmod(length, BLOCK)
        records = f"{whole}+{1 if rest else 0} records"
        errors = [n for n in raw.bad if start < (n + 1) * BLOCK and n * BLOCK < end]
        lines = [
            *(f"blk: {target}: I/O error at block {n}" for n in errors),
            f"{records} in", f"{records} out", f"{length} bytes copied",
        ]
        scene = block_scene(entry.path, destination, start, end, scanning, len(data), errors)

        if real:
            def finish(item, before):
                fileops.apply(context, item.path, destination, False)
                if item.session_file is not None:
                    item.session_file.state = before                   # у исходника слой остаётся, снят он только с копии
                    item.session_file.save(update_fields=["state"])
                else:
                    SessionFile.objects.filter(session=context.session, path=item.path).update(state=before)
                return f"  {destination}"

            result = self.unlock(context, target, [str(int(top.params["skip"]))], self.layer, finish=finish, scene=lambda *_: scene)
            if result.exit_code != 0:
                return result
            return CommandResult("\n".join([*lines, result.output]), 0, scene=scene, effects=result.effects)

        slices.make(context.session, entry.machine_file, raw_state, start, end, destination)
        return CommandResult("\n".join([*lines, f"blk: {target}: {self.done}", f"  {destination}"]), 0, scene=scene)


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

