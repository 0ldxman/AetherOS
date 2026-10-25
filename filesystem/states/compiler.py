"""Проверка разобранного стека по реестру (шаг 3).

Проверяет слои и их аргументы (слой существует, аргументы известны,
обязательные заданы, значения нужного типа) и хуки (известные события и
действия, форма аргументов действия) и подстановки `{...}` в текстах.
Имена команд в ответах слоя (`ftyp: ...`) и содержимое путей пока не
проверяются.

compile_text(text) -> list[CompiledLayer] или StateError со ВСЕМИ ошибками.
"""

import difflib
import re
from dataclasses import dataclass
from string import Formatter
from typing import Any

from filesystem.states.base import BaseState, Param
from filesystem.states.hooks import (
    ACTIONS,
    MAIL_ACTIONS,
    EVENTS,
    GLOBAL_PLACEHOLDERS,
    PATH_ACTIONS,
    TEXT_ACTIONS,
)
from filesystem.states.parser import Action, Arg, Layer, Problem, parse, tokenize
from filesystem.states.registry import StateRegistry
from filesystem.states.registry import registry as default_registry

_TYPE_NAMES = {
    str: "текстом",
    int: "целым числом",
    float: "числом",
    bool: "«да» или «нет»",
}

_TRUE = {"true", "yes", "1", "да", "вкл"}
_FALSE = {"false", "no", "0", "нет", "выкл"}


class StateError(ValueError):
    """Текст стека не прошёл разбор или проверку. Содержит ВСЕ ошибки."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(str(p) for p in self.problems))


@dataclass
class CompiledLayer:
    layer: Layer
    state: type[BaseState]
    params: dict[str, Any]


def _suggest(word: str, options) -> str:
    matches = difflib.get_close_matches(word, list(options), n=1, cutoff=0.6)
    return f" Возможно, «{matches[0]}»?" if matches else ""


def _param_names(cls: type[BaseState]) -> str:
    return ", ".join(p.name for p in cls.params) or "нет"


def _convert(p: Param, arg: Arg) -> tuple[Any, str | None]:
    value = arg.value

    if p.type is str:
        if not value and p.required:
            return None, f"аргумент «{p.name}» не может быть пустым"

        return value, None

    if p.type is bool:
        low = value.lower()

        if low in _TRUE:
            return True, None

        if low in _FALSE:
            return False, None
    else:
        try:
            return p.type(value), None
        except ValueError:
            pass

    return None, (
        f"аргумент «{p.name}» должен быть {_TYPE_NAMES[p.type]}, а не «{value}»"
    )


def bind_params(
    cls: type[BaseState], args: list[Arg], line: int
) -> tuple[dict[str, Any], list[Problem]]:
    """Раскладывает аргументы из текста по параметрам класса слоя."""
    problems: list[Problem] = []
    raw: dict[str, Arg] = {}

    main = next((p for p in cls.params if p.positional), None)
    by_name = {p.name: p for p in cls.params}
    positional = [a for a in args if a.key is None]
    named = [a for a in args if a.key is not None]

    if positional:
        if main is None:
            problems.append(Problem(
                line,
                f"слой «{cls.name}» не принимает значение без имени "
                f"«{positional[0].value}». Аргументы: {_param_names(cls)}",
            ))
        else:
            raw[main.name] = positional[0]

            if len(positional) > 1:
                problems.append(Problem(
                    line,
                    f"лишнее значение «{positional[1].value}»: основной аргумент "
                    f"слоя «{cls.name}» один ({main.name}), остальные пишутся "
                    "как имя=значение",
                ))

    for arg in named:
        p = by_name.get(arg.key)

        if p is None:
            problems.append(Problem(
                line,
                f"у слоя «{cls.name}» нет аргумента «{arg.key}».{_suggest(arg.key, by_name)} "
                f"Есть: {_param_names(cls)}",
            ))
            continue

        if p.name in raw:
            problems.append(Problem(line, f"аргумент «{p.name}» указан дважды"))
            continue

        raw[p.name] = arg

    params: dict[str, Any] = {}

    for p in cls.params:
        arg = raw.get(p.name)

        if arg is None:
            if p.required:
                problems.append(Problem(
                    line, f"слою «{cls.name}» не хватает аргумента «{p.name}»"
                ))
            else:
                params[p.name] = p.default

            continue

        value, err = _convert(p, arg)

        if err:
            problems.append(Problem(line, err))
        else:
            params[p.name] = value

    return params, problems


def _check_text(
    text: str, allowed: set[str], line: int, what: str
) -> list[Problem]:
    """Проверяет подстановки {имя} в тексте. Разрешено только простое имя
    из списка allowed. Буквальные скобки пишутся удвоенными: {{ и }}."""
    if not text.strip():
        return [Problem(line, f"{what}: пустой текст")]

    try:
        fields = list(Formatter().parse(text))
    except ValueError:
        return [Problem(
            line,
            f"{what}: ошибка в фигурных скобках. Одиночные «{{» и «}}» "
            "не допускаются, буквальные скобки пишутся удвоенными: {{ и }}",
        )]

    problems: list[Problem] = []

    for _, field_name, spec, conversion in fields:
        if field_name is None:
            continue

        if not field_name:
            problems.append(Problem(
                line, f"{what}: пустые скобки {{}}, внутри должно быть имя"
            ))
        elif not field_name.isidentifier():
            problems.append(Problem(
                line,
                f"{what}: в «{{{field_name}}}» допустимо только имя переменной",
            ))
        elif spec or conversion:
            problems.append(Problem(
                line,
                f"{what}: форматирование внутри «{{{field_name}}}» "
                "не поддерживается",
            ))
        elif field_name not in allowed:
            problems.append(Problem(
                line, f"{what}: неизвестная переменная «{{{field_name}}}»"
            ))

    return problems


MAIL_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
MAIL_MAX_DELAY = 7 * 24 * 3600


def parse_mail(action: Action):
    """mail <письмо> [delay=секунды] -> (slug, секунды) или (None, текст ошибки)."""
    if action.quoted:
        return None, "«mail»: идентификатор письма пишется без кавычек"

    args, err = tokenize(action.value)

    if err:
        return None, err

    if not args or args[0].key is not None:
        return None, "«mail» требует идентификатор письма: mail door_open"

    slug = args[0].value

    if not MAIL_SLUG.match(slug):
        return None, f"«mail»: идентификатор «{slug}» не подходит (строчные латинские буквы, цифры, «-» и «_»)"

    delay = 0

    for extra in args[1:]:
        if extra.key != "delay":
            return None, "«mail» принимает только delay=секунды"

        try:
            delay = int(extra.value)
        except ValueError:
            return None, f"«mail»: delay должен быть целым числом секунд, а не «{extra.value}»"

        if not 0 <= delay <= MAIL_MAX_DELAY:
            return None, f"«mail»: delay от 0 до {MAIL_MAX_DELAY} секунд"

    return (slug, delay), None


def _check_mail(action: Action) -> list[Problem]:
    parsed, error = parse_mail(action)
    return [Problem(action.line, error)] if error else []


def _check_action(
    action: Action, registry: StateRegistry, allowed: set[str]
) -> list[Problem]:
    line = action.line
    name = action.name

    if name not in ACTIONS:
        return [Problem(line, f"неизвестное действие «{name}»")]

    if name in TEXT_ACTIONS:
        return _check_text(action.value, allowed, line, f"«{name}»")

    if name in PATH_ACTIONS:
        if action.quoted:
            if not action.value.strip():
                return [Problem(line, f"«{name}»: пустой путь")]

            return []

        args, err = tokenize(action.value)

        if err:
            return [Problem(line, err)]

        if len(args) != 1 or args[0].key is not None:
            return [Problem(line, f"«{name}» принимает ровно один путь")]

        return []

    if name in MAIL_ACTIONS:
        return _check_mail(action)

    # add <слой> [аргументы]
    if action.quoted:
        return [Problem(line, "«add»: имя слоя пишется без кавычек")]

    args, err = tokenize(action.value)

    if err:
        return [Problem(line, err)]

    if not args or args[0].key is not None:
        return [Problem(line, "«add» требует имя слоя: add damaged")]

    target = registry.get(args[0].value)

    if target is None:
        return [Problem(line, f"«add»: неизвестный слой «{args[0].value}»")]

    _, problems = bind_params(target, args[1:], line)
    return problems


def _check_hooks(
    layer: Layer, registry: StateRegistry, allowed: set[str]
) -> list[Problem]:
    problems: list[Problem] = []

    for hook in layer.hooks:
        if hook.event not in EVENTS:
            problems.append(Problem(hook.line, f"неизвестное событие «{hook.event}»"))
            continue

        if not hook.actions:
            problems.append(Problem(hook.line, f"у «on {hook.event}» нет действий"))

        for action in hook.actions:
            problems += _check_action(action, registry, allowed)

    return problems


def check_default_hooks(
    cls: type[BaseState], registry: StateRegistry
) -> list[Problem]:
    """Проверяет BaseState.default_hooks слоя теми же правилами, что и
    хуки в описании файла."""
    if not cls.default_hooks.strip():
        return []

    layers, problems = parse(f"> {cls.name}\n{cls.default_hooks}")

    if layers:
        layer = layers[0]

        if layer.overrides or layer.move:
            problems.append(Problem(
                0, "в default_hooks допустимы только блоки «on событие:»"
            ))

        allowed = (
            set(GLOBAL_PLACEHOLDERS)
            | set(cls.placeholders)
            | {p.name for p in cls.params}
        )
        problems += _check_hooks(layer, registry, allowed)

    return problems


def validate_defaults(registry: StateRegistry = default_registry):
    """Проверяет умолчания всех слоёв реестра. Ошибка здесь -- ошибка
    программиста, поэтому ValueError, а не StateError."""
    lines = []

    for name in registry.names():
        cls = registry.get(name)

        for problem in check_default_hooks(cls, registry):
            where = f"строка {problem.line - 1}" if problem.line else "общая"
            lines.append(f"{cls.__name__}.default_hooks, {where}: {problem.message}")

    if lines:
        raise ValueError("\n".join(lines))


def compile_layers(
    layers: list[Layer], registry: StateRegistry = default_registry
) -> tuple[list[CompiledLayer], list[Problem]]:
    compiled: list[CompiledLayer] = []
    problems: list[Problem] = []

    for layer in layers:
        cls = registry.get(layer.name)

        if cls is None:
            known = ", ".join(registry.names()) or "—"
            problems.append(Problem(
                layer.line,
                f"неизвестный слой «{layer.name}».{_suggest(layer.name, registry.names())} "
                f"Доступные: {known}",
            ))
            continue

        params, errors = bind_params(cls, layer.args, layer.line)
        problems += errors

        # Подстановки: общие, свои у слоя и значения его аргументов.
        allowed = (
            set(GLOBAL_PLACEHOLDERS)
            | set(cls.placeholders)
            | {p.name for p in cls.params}
        )

        for override in layer.overrides.values():
            problems += _check_text(
                override.text,
                allowed,
                override.line,
                f"ответ на «{override.command}»",
            )

        problems += _check_hooks(layer, registry, allowed)
        compiled.append(CompiledLayer(layer, cls, params))

    return compiled, problems


def compile_text(
    text: str, registry: StateRegistry = default_registry
) -> list[CompiledLayer]:
    layers, problems = parse(text)
    compiled, more = compile_layers(layers, registry)
    problems = sorted(problems + more, key=lambda p: p.line)

    if problems:
        raise StateError(problems)

    return compiled