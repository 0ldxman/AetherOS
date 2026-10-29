"""Язык сцен для автора: текст, который превращается в обычную сцену (scenes.engine.Scene).

Строка без префикса это вывод (say): цвета, {параметры}, <rand>, <since> и <table> как в приветствии (scenes.markup).
    ~ текст                          тусклая строка целиком
    \\@ текст, \\~ текст              строка, которая начинается с @ или ~
Внутри строки (без таблицы):
    <count to=64000 unit=K ms=600-1100/>   число растёт до значения прямо в строке; итог пишется текстом рядом
    <type speed=22 human typo chunk=3>текст</type>   текст печатается побуквенно
    <mark имя>текст</mark>                 пометка, которую потом портит @glitch имя | новый текст
Шаги, по строке на шаг (части разделяются |, необязательное после них ключ=значение):
    @blank [n]   @wait мс   @read [per_char=5 min=900 max=4500]   @clear   @cut   @flash
    @task метка | результат | мс      look=unit|kernel  note=…  done=…  style=…  at=секунды
    @bar метка | мс                   width=24
    @count метка | до | единица | мс  result=OK  note=…     (число с подписью отдельной строкой)
    @log секунды | тег | сообщение    style=…
    @glitch имя | новый текст         frames=14
    @countdown Старт через {n}с... | секунд
    @include слаг                     вставить другую сцену
Блоки (строки блока начинаются с пробела):
    @bars width=14                    @burst gap=8-45
      подпись | мс | результат | стоп%        строки с разметкой, как обычный вывод
Время мс: число или диапазон 200-450 (при каждом показе своё)."""
import re
from datetime import datetime, timezone

from scenes import markup
from scenes.engine import Scene, SceneError

MAX_DEPTH = 8
_PROBE = datetime(2030, 1, 1, tzinfo=timezone.utc)

_COUNT = re.compile(r"<count\b([^>]*?)/>")
_TYPE = re.compile(r"<type\b([^>]*)>(.*?)</type>")
_MARK = re.compile(r"<mark\s+(\w+)>")
_MARK_END = "</mark>"
_ATTR = re.compile(r'(\w+)(?:=("[^"]*"|\S+))?')
_SPLIT = re.compile("(\\d+)|(\\d+)|")
_STEP = re.compile(r"^@(\w+)\s*(.*)$")


class ScriptError(ValueError):
    pass


def _attrs(text):
    """Атрибуты тега: ключ=значение, ключ без значения это флаг. Кавычки для значений с пробелами."""
    return {key: (value.strip('"') if value else True) for key, value in _ATTR.findall(text)}


def _delay(text):
    """«450» или «200-450» -> число или пара."""
    found = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", str(text))
    if not found:
        raise ScriptError(f"ожидалось число миллисекунд (450) или диапазон (200-450), а не «{text}»")
    return int(found.group(1)) if found.group(2) is None else (int(found.group(1)), int(found.group(2)))


def _int(text, name):
    try:
        return int(str(text).strip())
    except ValueError:
        raise ScriptError(f"{name}: нужно целое число, а не «{text}»") from None


def _float(text, name):
    try:
        return float(str(text).strip())
    except ValueError:
        raise ScriptError(f"{name}: нужно число, а не «{text}»") from None


class _Compiler:
    def __init__(self, params, now, resolve, scene):
        self.params, self.now, self.resolve = params, now, resolve
        self.scene = scene
        self.errors = []
        self.stack = []

    # ---------- текст ----------

    def plain(self, text, line, extra=None):
        """Текст шага (метки, сообщения): подстановки и <rand>/<since>, без цветов."""
        parts, found = markup.parse_line(text, {**self.params, **(extra or {})}, self.now)
        self.errors += [(line, message) for message in found]
        return "".join(part for part, _ in parts)

    def inline(self, line, number):
        """Строка с тегами <count>, <type>, <mark> -> строка для markup и список вставок."""
        items = []

        def count(match):
            attrs = _attrs(match.group(1))
            try:
                items.append(("count", {"to": _int(attrs.get("to", ""), "count: to"), "unit": attrs.get("unit", "") or "",
                                        "ms": _delay(attrs.get("ms", "1400"))}))
            except ScriptError as error:
                self.errors.append((number, f"<count>: {error}"))
                return "?"
            return f"{len(items) - 1}"

        def typing(match):
            attrs = _attrs(match.group(1))
            try:
                items.append(("type", {
                    "value": self.plain(match.group(2), number), "speed": _int(attrs.get("speed", 22), "type: speed"),
                    "human": bool(attrs.get("human")), "typo": bool(attrs.get("typo")), "chunk": _int(attrs.get("chunk", 1), "type: chunk"),
                }))
            except ScriptError as error:
                self.errors.append((number, f"<type>: {error}"))
                return ""
            return f"{len(items) - 1}"

        def mark(match):
            items.append(("mark", match.group(1)))
            return f"{len(items) - 1}"

        line = _COUNT.sub(count, line)
        line = _TYPE.sub(typing, line)
        line = _MARK.sub(mark, line).replace(_MARK_END, "")
        return line, items

    def emit(self, parts, items):
        """Части строки (в них пометки вставок) -> шаги сцены: текст кусками, вставки между ними."""
        pending, mark = [], None

        def flush():
            if pending:
                self.scene.say(*pending, end=False)
                pending.clear()

        for text, style in parts:
            position = 0
            for found in _SPLIT.finditer(text):
                if found.start() > position:
                    pending.append((text[position:found.start()], style, mark))
                position = found.end()
                if found.group(1) is not None:
                    flush()
                    kind, data = items[int(found.group(1))]
                    tmp = Scene()
                    if kind == "count":
                        tmp.count("", data["to"], unit=data["unit"], ms=data["ms"], width=0)
                    else:
                        tmp.type(data["value"], speed=data["speed"], human=data["human"], typo=data["typo"], chunk=data["chunk"], end=False)
                    self.scene.steps.append(tmp.steps[0])
                elif found.group(2) is not None:
                    mark = items[int(found.group(2))][1]
                else:
                    mark = None
            if position < len(text):
                pending.append((text[position:], style, mark))
        flush()
        self.scene.blank()

    def say(self, line, number, style=None):
        text, items = self.inline(line, number)
        parts, found = markup.parse_line(text, self.params, self.now)
        self.errors += [(number, message) for message in found]
        if style:
            parts = [(part, style_ or style) for part, style_ in parts]
        if not parts:
            self.scene.blank()
        else:
            self.emit(parts, items)

    # ---------- шаги ----------

    def run(self, source):
        lines = source.splitlines()
        index = 0
        while index < len(lines):
            line, number = lines[index], index + 1
            index += 1
            try:
                index = self.line(lines, index, line, number)
            except (ScriptError, SceneError) as error:
                self.errors.append((number, str(error)))

    def line(self, lines, index, line, number):
        if not line.strip():
            self.scene.blank()
        elif markup._TABLE.match(line):
            end = next((i for i in range(index, len(lines)) if markup._END_TABLE.match(lines[i])), None)
            block = lines[index - 1:(end + 1 if end is not None else len(lines))]
            rows, found = markup.compile_lines("\n".join(block), self.params, self.now)
            self.errors += [(number - 1 + n, message) for n, message in found]
            for parts in rows:
                self.scene.say(*parts) if parts else self.scene.blank()
            return (end + 1) if end is not None else len(lines)
        elif line.startswith("\\@") or line.startswith("\\~"):
            self.say(line[1:], number)
        elif line.startswith("~ ") or line == "~":
            self.say(line[2:], number, style="dim")
        elif line.startswith("@"):
            return self.step(lines, index, line, number)
        else:
            self.say(line, number)
        return index

    def block(self, lines, index):
        """Строки блока: подряд идущие, начинаются с пробела."""
        rows = []
        while index < len(lines) and lines[index][:1] in (" ", "\t") and lines[index].strip():
            rows.append((index + 1, lines[index].strip()))
            index += 1
        return rows, index

    def step(self, lines, index, line, number):
        found = _STEP.match(line)
        if not found:
            raise ScriptError("после @ нужно имя шага")
        name, rest = found.group(1), found.group(2).strip()
        pieces = [piece.strip() for piece in markup._cells(rest)] if rest else []
        options = {}

        def split_options(count):
            """Позиционные части (первые count) и ключ=значение после них."""
            positional = pieces[:count]
            for piece in pieces[count:]:
                key, _, value = piece.partition("=")
                if not value or not key.strip().isidentifier():
                    raise ScriptError(f"@{name}: лишняя часть «{piece}»; необязательное пишется ключ=значение")
                options[key.strip()] = value.strip()
            return positional

        def pad(values, count):
            return values + [None] * (count - len(values))

        s = self.scene
        if name == "blank":
            s.blank(_int(rest or 1, "@blank"))
        elif name == "wait":
            s.wait(_delay(rest))
        elif name == "read":
            for piece in rest.split():
                key, _, value = piece.partition("=")
                options[key] = value
            s.read(per_char=_int(options.get("per_char", 4), "per_char"), min_ms=_int(options.get("min", 900), "min"),
                   max_ms=_int(options.get("max", 4500), "max"))
        elif name in ("clear", "cut", "flash"):
            getattr(s, name)()
        elif name == "task":
            label, result, ms = pad(split_options(3), 3)
            if not label:
                raise ScriptError("@task: нужна метка")
            kwargs = {"ms": _delay(ms) if ms else 600}
            if "at" in options:
                kwargs["at"] = _float(options["at"], "at")
            for key in ("look", "style", "note", "done"):
                if key in options:
                    kwargs[key] = self.plain(options[key], number)
            s.task(self.plain(label, number).rstrip() + " ", self.plain(result or "OK", number), **kwargs)
        elif name == "bar":
            label, ms = pad(split_options(2), 2)
            if not label:
                raise ScriptError("@bar: нужна метка")
            s.bar(self.plain(label, number).rstrip() + " ", ms=_delay(ms) if ms else 1200, width=_int(options.get("width", 24), "width"))
        elif name == "count":
            label, to, unit, ms = pad(split_options(4), 4)
            if not label or to is None:
                raise ScriptError("@count: нужны метка и число: @count метка | до | единица | мс")
            s.count(self.plain(label, number), _int(to, "@count"), unit=unit or "", ms=_delay(ms) if ms else 1400,
                    result=options.get("result"), note=self.plain(options["note"], number) if "note" in options else None)
        elif name == "log":
            at, tag, message = pad(split_options(3), 3)
            if None in (at, tag, message):
                raise ScriptError("@log: @log секунды | тег | сообщение")
            s.log(_float(at, "@log"), self.plain(tag, number), self.plain(message, number), style=options.get("style"))
        elif name == "glitch":
            target, to = pad(split_options(2), 2)
            if not target or to is None:
                raise ScriptError("@glitch: @glitch имя | новый текст")
            s.glitch(target, self.plain(to, number), frames=_int(options.get("frames", 14), "frames"))
        elif name == "countdown":
            template, seconds = pad(split_options(2), 2)
            if not template or seconds is None:
                raise ScriptError("@countdown: @countdown Старт через {n}с... | секунд")
            s.countdown(self.plain(template, number, {"n": "{n}"}), _int(seconds, "@countdown"))
        elif name == "include":
            self.include(rest, number)
        elif name in ("bars", "burst"):
            for piece in rest.split():
                key, _, value = piece.partition("=")
                options[key] = value
            rows, index = self.block(lines, index)
            if not rows:
                raise ScriptError(f"@{name}: после шага нужны строки блока (с отступом)")
            if name == "bars":
                table = []
                for row_number, text in rows:
                    cells = [cell.strip() for cell in markup._cells(text)]
                    if len(cells) < 2:
                        self.errors.append((row_number, "строка полосы: подпись | мс | результат | стоп%"))
                        continue
                    label, ms, *rest_cells = cells
                    row = [self.plain(label, row_number), _delay(ms)]
                    if rest_cells and rest_cells[0]:
                        row.append(rest_cells[0])
                    if len(rest_cells) > 1 and rest_cells[1]:
                        row.append(_int(rest_cells[1], "стоп"))
                    table.append(tuple(row))
                if table:
                    s.bars(table, width=_int(options.get("width", 14), "width"))
            else:
                gap = _delay(options["gap"]) if options.get("gap") else (8, 45)
                for row_number, text in rows:
                    inner, items = self.inline(text, row_number)
                    parts, found_errors = markup.parse_line(inner, self.params, self.now)
                    self.errors += [(row_number, message) for message in found_errors]
                    self.emit(parts, items) if parts else s.blank()
                    s.wait(gap)
        else:
            raise ScriptError(f"неизвестный шаг @{name}")
        return index

    def include(self, slug, number):
        if not slug:
            raise ScriptError("@include: нужен слаг сцены")
        if slug in self.stack or len(self.stack) >= MAX_DEPTH:
            raise ScriptError(f"@include {slug}: сцены вставляют друг друга по кругу")
        text = self.resolve(slug) if self.resolve else None
        if text is None:
            raise ScriptError(f"@include {slug}: такой сцены нет")
        inner = _Compiler(self.params, self.now, self.resolve, self.scene)
        inner.stack = [*self.stack, slug]
        inner.run(text)
        self.errors += [(number, f"в «{slug}» строка {n}: {m}") for n, m in inner.errors]


def compile_script(source, params, now=None, resolve=None, scene=None):
    """Текст сцены -> (Scene, ошибки [(номер строки с 1, текст)]). resolve(слаг) даёт текст другой сцены для @include или None."""
    compiler = _Compiler(params, now, resolve, scene or Scene())
    compiler.run(source)
    return compiler.scene, compiler.errors


def check_script(source, names, resolve=None):
    """Ошибки текста сцены без проигрывания: подстановки и «сейчас» условные."""
    return compile_script(source, dict.fromkeys(names, ""), _PROBE, resolve)[1]
