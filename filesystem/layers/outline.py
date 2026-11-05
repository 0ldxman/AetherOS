"""Конструктор слоёв: текст стека <-> структура, без потерь.

Текст остаётся источником правды (поле Item.state). Конструктор правит только заголовок каждого слоя: имя, значения
аргументов и `->`/`=>`. Всё, что идёт под заголовком (ответы слоя, хуки, комментарии), и всё, что стоит до первого слоя,
хранится как есть и возвращается обратно нетронутым.

    outline(text)        -> Outline: слои с их значениями или причина, почему конструктором такой текст не править
    build(preamble, layers) -> text
    catalog()            -> описание слоёв для формы (названия, аргументы, подсказки)
"""
from dataclasses import dataclass, field

from filesystem.layers.parser import MOVE_OPERATORS, parse
from filesystem.layers.registry import registry

_TYPE_NAMES = {str: "str", int: "int", float: "float", bool: "bool"}


@dataclass
class OutlineLayer:
    name: str
    values: dict[str, str] = field(default_factory=dict)       # имя аргумента -> значение (всё строками, как в тексте)
    move: tuple[str, str] | None = None                         # ("rename" | "copy", путь)
    body: str = ""                                              # ответы, хуки и комментарии под заголовком, как написано


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
        result.layers.append(OutlineLayer(
            name=layer.name, values=values,
            move=(layer.move.kind, layer.move.target) if layer.move else None,
            body="\n".join(lines[layer.line: end - 1]).strip("\n"),
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
        if layer.body.strip():
            rows.append(layer.body.strip("\n"))
    return "\n".join(rows)
