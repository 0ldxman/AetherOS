"""Работа слоя во время игры (шаг 2, часть а): ответ на информационную команду.

Слой отвечает текстом автора файла (`ftyp: ...`), а если его нет -- текстом
по умолчанию из класса слоя (BaseState.answers). Нет ни того ни другого --
слой молчит (None), команда идёт дальше по стеку.

Какие переменные доступны в тексте, проверяется при сохранении файла
(compiler). Значения для них здесь передаёт вызывающий код.
"""

from functools import cache
from typing import Any, Mapping

from filesystem.states.base import BaseState
from filesystem.states.compiler import CompiledLayer
from filesystem.states.parser import Action, Hook, parse


def layer_variables(
    compiled: CompiledLayer, *, path: str, name: str, **extra: Any
) -> dict[str, Any]:
    """Значения для подстановок {...}: общие (path, name), аргументы слоя
    и собственные переменные слоя (extra, например attempts_left)."""
    return {"path": path, "name": name, **compiled.params, **extra}


def render(text: str, variables: Mapping[str, Any]) -> str:
    """Подставляет значения. Если для переменной значения не передали,
    будет KeyError: это ошибка вызывающего кода, а не админа."""
    return text.format_map(variables)


def answer(
    compiled: CompiledLayer, command: str, variables: Mapping[str, Any]
) -> str | None:
    """Ответ слоя на команду или None, если слой на неё не отвечает."""
    override = compiled.layer.overrides.get(command)

    if override is not None:
        return render(override.text, variables)

    default = compiled.state.answers.get(command)

    if default is not None:
        return render(default, variables)

    return None


@cache
def default_hooks(cls: type[BaseState]) -> tuple[Hook, ...]:
    """Хуки слоя по умолчанию, разобранные из BaseState.default_hooks."""
    if not cls.default_hooks.strip():
        return ()

    layers, problems = parse(f"> {cls.name}\n{cls.default_hooks}")

    if problems or not layers:
        raise ValueError(
            f"{cls.__name__}.default_hooks не разобран: "
            + "; ".join(str(p) for p in problems)
        )

    return tuple(layers[0].hooks)


def actions_for(compiled: CompiledLayer, event: str) -> list[Action]:
    """Действия слоя на событие.

    Хук автора файла (`on событие:`) целиком заменяет умолчание этого
    события; если автор его не писал, действует умолчание класса слоя.
    Сокращение `-> b.bin` у заголовка слоя -- это rename (или `=>` copy) на
    событие remove: оно выполняется первым и умолчания не заменяет."""
    actions: list[Action] = []
    layer = compiled.layer

    if event == "remove" and layer.move is not None:
        actions.append(
            Action(layer.move.kind, layer.move.line, layer.move.target)
        )

    own = next((h for h in layer.hooks if h.event == event), None)

    if own is not None:
        actions.extend(own.actions)
    else:
        default = next(
            (h for h in default_hooks(compiled.state) if h.event == event), None
        )

        if default is not None:
            actions.extend(default.actions)

    return actions