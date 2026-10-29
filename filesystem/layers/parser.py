"""Парсер текста стека (шаг 1): текст -> список слоёв.

Парсер смотрит только на форму текста. Существует ли слой, команда,
событие или действие, он не проверяет: это дело следующих шагов.

Формат:

    # комментарий
    > corrupted -> b.bin              слой; -> переименовать, => копировать
    file: Header checksum mismatch    ответ слоя на команду (до конца строки)
    strings: "многострочный
    текст в кавычках"
    on remove:                        хук со списком действий
    - say "Готово"
    - add damaged
    on fail: say "Не то"              хук с одним действием в строке

    > encrypted hunter2 attempts=3    главный аргумент без имени, остальные имя=значение

Пробелы в начале строк ничего не значат. Парсер не останавливается на
первой ошибке, а собирает все.
"""

import re
from dataclasses import dataclass, field

MOVE_OPERATORS = {"->": "rename", "=>": "copy"}

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HOOK = re.compile(r"^on\s+([\w-]+)\s*:(.*)$")
_OVERRIDE = re.compile(r"^([A-Za-z_][\w-]*)\s*:(.*)$")


@dataclass(frozen=True)
class Problem:
    line: int
    message: str

    def __str__(self):
        return f"строка {self.line}: {self.message}"


@dataclass
class Arg:
    """`hunter2` (key=None) или `attempts=3` (key='attempts')."""

    value: str
    key: str | None = None
    quoted: bool = False


@dataclass
class Override:
    """`file: текст` -- свой ответ слоя на команду."""

    command: str
    text: str
    line: int


@dataclass
class Action:
    """Строка действия хука: имя и всё, что после него.

    value -- остаток строки как есть. Если он был в кавычках, то уже
    без кавычек и с развёрнутым экранированием (quoted=True). Как его
    читать (текст или аргументы), решает следующий шаг.
    """

    name: str
    line: int
    value: str = ""
    quoted: bool = False


@dataclass
class Hook:
    event: str
    line: int
    actions: list[Action] = field(default_factory=list)


@dataclass
class Move:
    """`-> путь` (rename) или `=> путь` (copy) в заголовке слоя."""

    kind: str
    target: str
    line: int


@dataclass
class Layer:
    name: str
    line: int
    args: list[Arg] = field(default_factory=list)
    move: Move | None = None
    overrides: dict[str, Override] = field(default_factory=dict)
    hooks: list[Hook] = field(default_factory=list)


def tokenize(source: str) -> tuple[list[Arg], str | None]:
    """Делит строку на аргументы. Значение с пробелами берётся в кавычки,
    внутри кавычек \\" и \\\\ -- экранирование. `ключ=значение` распознаётся,
    только если ключ без кавычек. Возвращает (аргументы, текст ошибки)."""
    args: list[Arg] = []
    i, n = 0, len(source)

    while i < n:
        while i < n and source[i].isspace():
            i += 1

        if i >= n:
            break

        buf: list[str] = []
        key: str | None = None
        quoted = False

        while i < n and not source[i].isspace():
            c = source[i]

            if c == '"':
                quoted = True
                i += 1

                while True:
                    if i >= n:
                        return args, "не закрыта кавычка"

                    c = source[i]

                    if c == "\\" and i + 1 < n and source[i + 1] in '"\\':
                        buf.append(source[i + 1])
                        i += 2
                        continue

                    if c == '"':
                        i += 1
                        break

                    buf.append(c)
                    i += 1

                continue

            if (
                c == "="
                and key is None
                and not quoted
                and buf
                and _IDENT.match("".join(buf))
            ):
                key = "".join(buf)
                buf = []
                i += 1
                continue

            buf.append(c)
            i += 1

        args.append(Arg("".join(buf), key, quoted))

    return args, None


class _Parser:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.i = 0  # индекс следующей непрочитанной строки
        self.problems: list[Problem] = []
        self.layers: list[Layer] = []
        self.layer: Layer | None = None
        self.hook: Hook | None = None

    def error(self, line: int, message: str):
        self.problems.append(Problem(line, message))

    def run(self):
        while self.i < len(self.lines):
            lineno = self.i + 1
            line = self.lines[self.i].strip()
            self.i += 1

            if not line or line.startswith("#"):
                continue

            if line.startswith(">"):
                self._header(line[1:], lineno)
                continue

            if self.layer is None:
                self.error(
                    lineno,
                    "строка вне слоя: сначала нужен заголовок слоя вида «> имя»",
                )
                # «висящий» слой, чтобы не повторять ошибку на каждой строке
                self.layer = Layer(name="", line=lineno)

            if line == "-" or line.startswith("- "):
                self._action(line[1:], lineno)
                continue

            match = _HOOK.match(line)

            if match:
                self._hook(match.group(1), match.group(2), lineno)
                continue

            match = _OVERRIDE.match(line)

            if match:
                self._override(match.group(1), match.group(2), lineno)
                continue

            self.hook = None
            self.error(
                lineno,
                f"не понял строку «{line}». Текст ответа на несколько строк "
                "нужно взять в кавычки",
            )

    def _read_text(self, rest: str, start: int) -> tuple[str, bool]:
        """Текст до конца строки либо в кавычках (может идти на несколько
        строк). В кавычках экранируются только \\" и \\\\, остальные
        обратные слэши остаются как есть (\\x00 останется \\x00).
        Возвращает (текст, был_в_кавычках)."""
        text = rest.strip()

        if not text.startswith('"'):
            return text, False

        chunk = text[1:]
        buf: list[str] = []

        while True:
            j = 0

            while j < len(chunk):
                c = chunk[j]

                if c == "\\" and j + 1 < len(chunk) and chunk[j + 1] in '"\\':
                    buf.append(chunk[j + 1])
                    j += 2
                    continue

                if c == '"':
                    tail = chunk[j + 1:].strip()

                    if tail:
                        self.error(
                            start,
                            f"после закрывающей кавычки лишний текст: «{tail}»",
                        )

                    return "".join(buf), True

                buf.append(c)
                j += 1

            if self.i >= len(self.lines):
                self.error(start, "не закрыта кавычка")
                return "".join(buf), True

            buf.append("\n")
            chunk = self.lines[self.i]
            self.i += 1

    def _header(self, rest: str, lineno: int):
        self.hook = None
        layer = Layer(name="", line=lineno)
        self.layer = layer
        args, err = tokenize(rest)

        if err:
            self.error(lineno, err)
            return

        for index, arg in enumerate(args):
            if arg.quoted or arg.key is not None or arg.value not in MOVE_OPERATORS:
                continue

            target = args[index + 1:]
            args = args[:index]

            if len(target) != 1 or target[0].key is not None:
                self.error(lineno, f"после «{arg.value}» должен идти ровно один путь")
            else:
                layer.move = Move(MOVE_OPERATORS[arg.value], target[0].value, lineno)

            break

        if not args:
            self.error(lineno, "после «>» нужно имя слоя")
            return

        first = args[0]

        if first.key is not None or first.quoted:
            self.error(lineno, "имя слоя пишется без кавычек и без «=»")
            return

        layer.name = first.value
        layer.args = args[1:]
        self.layers.append(layer)

    def _override(self, command: str, rest: str, lineno: int):
        self.hook = None
        text, _ = self._read_text(rest, lineno)
        known = self.layer.overrides.get(command)

        if known:
            self.error(
                lineno, f"ответ на «{command}» уже задан в строке {known.line}"
            )
            return

        self.layer.overrides[command] = Override(command, text, lineno)

    def _hook(self, event: str, rest: str, lineno: int):
        hook = Hook(event, lineno)
        known = next((h for h in self.layer.hooks if h.event == event), None)

        if known:
            self.error(
                lineno,
                f"«on {event}» уже есть в этом слое (строка {known.line}); "
                "объедините действия в один список",
            )
        else:
            self.layer.hooks.append(hook)

        self.hook = hook

        if rest.strip():
            self._add_action(hook, rest, lineno)

    def _action(self, rest: str, lineno: int):
        if self.hook is None:
            self.error(
                lineno,
                "действие «-» вне списка: перед ним нужна строка «on событие:»",
            )
            return

        self._add_action(self.hook, rest, lineno)

    def _add_action(self, hook: Hook, rest: str, lineno: int):
        parts = rest.strip().split(None, 1)

        if not parts:
            self.error(lineno, "пустое действие")
            return

        value, quoted = self._read_text(parts[1] if len(parts) > 1 else "", lineno)
        hook.actions.append(Action(parts[0], lineno, value, quoted))


def parse(text: str) -> tuple[list[Layer], list[Problem]]:
    parser = _Parser(text or "")
    parser.run()
    return parser.layers, parser.problems