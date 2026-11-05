"""Конструктор слоёв: текст стека <-> структура, без потерь.

Текст остаётся источником правды (поле Item.state). Конструктор правит только заголовок каждого слоя: имя, значения
аргументов и `->`/`=>`. Всё, что идёт под заголовком (ответы слоя, хуки, комментарии), и всё, что стоит до первого слоя,
хранится как есть и возвращается обратно нетронутым.

    outline(text)        -> Outline: слои с их значениями или причина, почему конструктором такой текст не править
    build(preamble, layers) -> text
    catalog()            -> описание слоёв для формы (названия, аргументы, подсказки)
"""
from dataclasses import dataclass, field

from filesystem.layers.hooks import ACTIONS, EVENTS, TEXT_ACTIONS
from filesystem.layers.parser import MOVE_OPERATORS, parse
from filesystem.layers.registry import registry

_TYPE_NAMES = {str: "str", int: "int", float: "float", bool: "bool"}


@dataclass
class Answer:
    command: str
    text: str


@dataclass
class Action:
    name: str
    value: str = ""
    quoted: bool = False        # значение было в кавычках (для say и log кавычки ставятся всегда)


@dataclass
class Hook:
    event: str
    actions: list[Action] = field(default_factory=list)


@dataclass
class OutlineLayer:
    name: str
    values: dict[str, str] = field(default_factory=dict)       # имя аргумента -> значение (всё строками, как в тексте)
    move: tuple[str, str] | None = None                         # ("rename" | "copy", путь)
    body: str = ""                                              # ответы, хуки и комментарии под заголовком, как написано
    answers: list[Answer] | None = None                         # ответы слоя на команды; None: тело нельзя разложить (комментарии и т. п.)
    hooks: list[Hook] | None = None                             # события слоя с действиями; None вместе с answers


@dataclass
class Outline:
    layers: list[OutlineLayer] = field(default_factory=list)
    preamble: str = ""                                          # всё до первого слоя (комментарии)
    problems: list[tuple[int, str]] = field(default_factory=list)   # ошибки разбора: (строка, текст)
    unsupported: str = ""                                       # почему конструктор не может править этот текст

    @property
    def editable(self) -> bool:
        return not self.problems and not self.unsupported


def catalog() -> list[dict]:
    """Слои для формы: название, пояснение и аргументы с подписями. Строится из самих классов."""
    rows = []
    for name in registry.names():
        cls = registry._states[name]
        rows.append({
            "name": cls.name,
            "title": cls.title or cls.name,
            "summary": cls.summary,
            "params": [
                {
                    "name": p.name, "label": p.label or p.name, "type": _TYPE_NAMES[p.type], "required": p.required,
                    "positional": p.positional, "unlock": p.unlock, "help": p.help,
                    "default": None if p.default is None else str(p.default),
                }
                for p in cls.params
            ],
        })
    return rows


def outline(text: str) -> Outline:
    text = text or ""
    layers, problems = parse(text)
    if problems:
        return Outline(problems=[(p.line, p.message) for p in problems])
    lines = text.splitlines()
    result = Outline(preamble="\n".join(lines[: layers[0].line - 1]).rstrip() if layers else "\n".join(lines).rstrip())
    ends = [layer.line for layer in layers[1:]] + [len(lines) + 1]
    for layer, end in zip(layers, ends):
        cls = registry._states.get(layer.name)
        if cls is None:
            result.unsupported = f"слоя «{layer.name}» нет в каталоге"
            return result
        values, reason = _values(cls, layer)
        if reason:
            result.unsupported = f"слой «{layer.name}»: {reason}"
            return result
        body = "\n".join(lines[layer.line: end - 1]).strip("\n")
        parts = structure_of(body)
        result.layers.append(OutlineLayer(
            name=layer.name, values=values, move=(layer.move.kind, layer.move.target) if layer.move else None, body=body,
            answers=parts[0] if parts else None, hooks=parts[1] if parts else None,
        ))
    return result


def _values(cls, layer) -> tuple[dict[str, str], str]:
    by_name = {p.name: p for p in cls.params}
    positional = next((p for p in cls.params if p.positional), None)
    values: dict[str, str] = {}
    for arg in layer.args:
        if arg.key is None:
            if positional is None or positional.name in values:
                return {}, f"лишний аргумент «{arg.value}»"
            values[positional.name] = arg.value
        elif arg.key not in by_name or arg.key in values:
            return {}, f"неизвестный или повторный аргумент «{arg.key}»"
        else:
            values[arg.key] = arg.value
    return values, ""


def _quote(value: str) -> str:
    plain = value != "" and value not in MOVE_OPERATORS and not any(c.isspace() or c in '"\\=' for c in value)
    return value if plain else '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def steps(layers: list[OutlineLayer]) -> list[str]:
    """Для каждого слоя: какой командой игрок его снимет (пусто, если сказать нечего). Порядок тот же, что у слоёв."""
    rows = []
    for layer in layers:
        cls = registry._states.get(layer.name)
        values = {k: ("" if v is None else str(v).strip()) for k, v in layer.values.items()}
        rows.append(cls.how(values) if cls else "")
    return rows


def header(layer: OutlineLayer) -> str:
    cls = registry._states.get(layer.name)
    parts = [">", layer.name]
    for p in sorted(cls.params, key=lambda p: not p.positional) if cls else ():
        value = layer.values.get(p.name)
        value = "" if value is None else str(value).strip()
        if value == "":
            continue
        parts.append(_quote(value) if p.positional else f"{p.name}={_quote(value)}")
    if layer.move:
        parts += ["->" if layer.move[0] == "rename" else "=>", _quote(layer.move[1])]
    return " ".join(parts)


def build(preamble: str, layers: list[OutlineLayer]) -> str:
    """Текст стека из структуры. Позиционный аргумент идёт первым, остальные по порядку из каталога."""
    rows = [preamble.rstrip()] if preamble.strip() else []
    for layer in layers:
        rows.append(header(layer))
        body = _body(layer)
        if body.strip():
            rows.append(body.strip("\n"))
    return "\n".join(rows)


# ---- ответы и события слоя ----

def _quoted(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _answer_text(text: str) -> str:
    plain = text != "" and "\n" not in text and not text.startswith('"') and text == text.strip()
    return text if plain or text == "" else _quoted(text)


def _action_value(action: Action) -> str:
    value = action.value if "\n" in action.value else action.value.strip()
    if action.name in TEXT_ACTIONS or action.quoted:
        return _quoted(value) if value != "" or action.quoted else ""
    return value


def regen_body(answers: list[Answer], hooks: list[Hook]) -> str:
    """Тело слоя из ответов и событий: сначала ответы, потом хуки (`on событие:` и по строке на действие)."""
    rows = [f"{a.command}:" + (f" {_answer_text(a.text)}" if a.text != "" else "") for a in answers]
    for hook in hooks:
        rows.append(f"on {hook.event}:")
        for action in hook.actions:
            value = _action_value(action)
            rows.append(f"- {action.name}" + (f" {value}" if value != "" else ""))
    return "\n".join(rows)


def _shape(layers):
    return [
        ([(o.command, o.text) for o in layer.overrides.values()],
         [(h.event, [(a.name, a.value) for a in h.actions]) for h in layer.hooks])
        for layer in layers
    ]


def structure_of(body: str) -> tuple[list[Answer], list[Hook]] | None:
    """Ответы и события из тела слоя. None, если тело нельзя разложить и собрать обратно без потерь (есть комментарии,
    непонятные строки): такое тело правится текстом."""
    if any(row.strip().startswith("#") for row in body.splitlines()):
        return None
    layers, problems = parse("> x\n" + body)
    if problems or len(layers) != 1:
        return None
    layer = layers[0]
    answers = [Answer(o.command, o.text) for o in layer.overrides.values()]
    hooks = [Hook(h.event, [Action(a.name, a.value, a.quoted) for a in h.actions]) for h in layer.hooks]
    again, more = parse("> x\n" + regen_body(answers, hooks))
    if more or _shape(again) != _shape(layers):
        return None
    return answers, hooks


def _body(layer: OutlineLayer) -> str:
    """Тело при сборке: если ответы и события не менялись, остаётся как написано; изменились: собирается заново."""
    if layer.answers is None or layer.hooks is None:
        return layer.body
    if structure_of(layer.body) == (layer.answers, layer.hooks):
        return layer.body
    return regen_body(layer.answers, layer.hooks)


# Подписи для формы. Сами события и действия описаны в hooks.py; здесь только человеческий язык.
EVENT_TITLES = {
    "remove": ("Слой снят", "Срабатывает один раз, когда игрок снял этот слой."),
    "attempt": ("Неудачная попытка", "Срабатывает при каждой неверной попытке снять слой."),
    "fail": ("Попытки кончились", "Срабатывает один раз, когда попытки закончились."),
    "read": ("Файл открыт", "Игрок открыл файл командой cnt (каждый раз). Слой при этом остаётся."),
    "delete": ("Файл удалён", "Игрок удалил файл командой del: он ушёл в корзину (каждый раз)."),
    "restore": ("Файл возвращён из корзины", "Игрок вернул файл командой rcvr."),
}

# имя действия -> (название, подпись значения, пример, подсказка). Подпись пустая: у действия нет значения.
ACTION_TITLES = {
    "say": ("Сказать игроку", "Текст", "Готово. Осталось попыток: {attempts_left}", "Сообщение в терминале. Подстановки: {attempts_left}, {path}, {name}."),
    "log": ("Записать в журнал", "Текст", "Файл вскрыт: {path}", "Запись в журнал событий машины."),
    "add": ("Добавить слой", "Слой и его аргументы", "damaged", "Накладывает на файл ещё один слой, например damaged или encrypted pass."),
    "drop": ("Удалить файл", "Путь", "/home/secret.dat", "Удаляет файл у игрока. Относительный путь считается от текущего файла."),
    "rename": ("Переименовать файл", "Новый путь", "opened.txt", "Переименовывает файл у игрока."),
    "copy": ("Скопировать файл", "Куда", "backup/copy.txt", "Копирует файл у игрока."),
    "mail": ("Прислать письмо", "Письмо и задержка", "door_open delay=30", "Идентификатор письма из почты, затем при желании delay=секунды."),
    "kick": ("Выбросить из сессии", "", "", "Игрока выбрасывает на уровень выше или на экран входа."),
    "alert": ("Засыпать окнами ошибок", "Сообщение и параметры", "unreachable count=12 gap=300", "Сообщение из каталога системы, count — сколько окон, gap — пауза в мс."),
    "open": ("Открыть окно", "Адрес", "apps/wiki/go/harbor/", "Внутренний адрес окна. Адрес с пробелами или «=» пишется в кавычках."),
}

# Команды игрока, на которые слой может отвечать по-своему (любую другую тоже можно вписать).
ANSWER_COMMANDS = ("ftyp", "cnt", "ward", "pak", "rpr", "blk", "cvt")


def hooks_catalog() -> dict:
    return {
        "events": [{"name": name, "title": EVENT_TITLES[name][0], "help": EVENT_TITLES[name][1]} for name in EVENTS],
        "actions": [
            {"name": name, "title": ACTION_TITLES[name][0], "value_label": ACTION_TITLES[name][1], "example": ACTION_TITLES[name][2],
             "help": ACTION_TITLES[name][3], "text": name in TEXT_ACTIONS}
            for name in ACTIONS
        ],
        "commands": list(ANSWER_COMMANDS),
    }
