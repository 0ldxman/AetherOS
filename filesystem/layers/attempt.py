"""Одна попытка снять верхний слой, от текста до текста (шаг 7, часть а).

Склеивает уже готовые части в одну функцию:

    описание файла + сохранённый прогресс + значения игрока
        -> прогресс из JSON (stack.load_progress)
        -> эффективный стек (stack.build_stack)
        -> попытка снять слой (stack.remove_top)
        -> хуки (executor.run_events)
        -> новый прогресс в JSON

Django здесь нет: на вход и на выход идут строки. Чтение и запись
запись слоя игрока делает unlock.py.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from filesystem.layers.compiler import CompiledLayer, compile_text
from filesystem.layers.executor import HookOutcome, run_event, run_events
from filesystem.layers.registry import StateRegistry
from filesystem.layers.registry import registry as default_registry
from filesystem.layers.runtime import answer, layer_variables
from filesystem.layers.stack import (
    RemoveResult,
    attempts_left,
    build_stack,
    load_progress,
    remove_top,
)


@dataclass
class AttemptOutcome:
    result: RemoveResult  # слой снят или нет, какой слой, что неверно, события
    hooks: HookOutcome  # say, log и файловые операции после хуков
    state: str  # новый текст для PlayerFile.state


def attempt_remove(
    canonical_text: str,
    raw_state: str,
    *,
    path: str,
    name: str,
    given: Mapping[str, Any] | None = None,
    registry: StateRegistry = default_registry,
) -> AttemptOutcome:
    """canonical_text -- Item.state, raw_state -- PlayerFile.state,
    given -- значения игрока (имя аргумента -> значение, типы уже приведены).

    Ошибка в canonical_text (StateError) сюда доходить не должна: админка
    не даёт сохранить такой текст. Если дошла, она всплывает как есть."""
    canonical = (
        compile_text(canonical_text, registry) if canonical_text.strip() else []
    )

    progress = load_progress(raw_state, canonical_text)
    stack = build_stack(canonical, progress, registry)
    result = remove_top(stack, progress, given)
    hooks = run_events(result, progress, path=path, name=name, registry=registry)

    return AttemptOutcome(result, hooks, progress.dump())


@dataclass
class EventOutcome:
    hooks: HookOutcome  # что случилось по хукам события
    state: str  # новый текст для PlayerFile.state (хук мог добавить слой)


def fire_event(
    canonical_text: str,
    raw_state: str,
    event: str,
    *,
    path: str,
    name: str,
    registry: StateRegistry = default_registry,
) -> EventOutcome:
    """Событие, которое случилось с файлом само по себе (delete, restore), без попытки снять слой.

    Хуки на него берёт верхний слой файла, как и при остальных событиях. Нет слоёв: хуков нет."""
    canonical = (
        compile_text(canonical_text, registry) if canonical_text.strip() else []
    )
    progress = load_progress(raw_state, canonical_text)
    stack = build_stack(canonical, progress, registry)
    outcome = HookOutcome()

    if stack:
        variables = layer_variables(
            stack[0], path=path, name=name, attempts_left=attempts_left(stack, progress)
        )
        outcome = run_event(stack[0], event, progress, variables, registry)

    return EventOutcome(outcome, progress.dump())


def top_answer(
    canonical_text: str,
    raw_state: str,
    command: str,
    *,
    path: str,
    name: str,
    only_top: bool = False,
    registry: StateRegistry = default_registry,
) -> str | None:
    """Ответ файла на информационную команду (ftyp, txtx и т.п.).

    Слои опрашиваются сверху вниз: отвечает первый, у кого есть текст
    (свой от автора файла или умолчание класса). Если не ответил никто,
    результат None, а что тогда сказать, решает команда.

    only_top=True: спрашивать только верхний слой. Так отвечает команда,
    которая снимает слои (ward), когда верхний слой не её: нижние слои
    в этот момент до файла «не достают».

    Прогресс только читается и нигде не сохраняется."""
    canonical = (
        compile_text(canonical_text, registry) if canonical_text.strip() else []
    )

    progress = load_progress(raw_state, canonical_text)
    stack = build_stack(canonical, progress, registry)

    for index, layer in enumerate(stack[:1] if only_top else stack):
        # Попытки тратятся только у верхнего слоя, у нижних они целые.
        if index == 0:
            left = attempts_left(stack, progress)
        else:
            left = layer.state.max_attempts(layer.params)

        variables = layer_variables(
            layer, path=path, name=name, attempts_left=left
        )
        text = answer(layer, command, variables)

        if text is not None:
            return text

    return None


def peek_top(
    canonical_text: str,
    raw_state: str,
    registry: StateRegistry = default_registry,
) -> CompiledLayer | None:
    """Верхний слой файла сейчас (None -- слоёв нет). Ничего не меняет и не
    сохраняет. Команды, которые снимают слои, смотрят по нему, их ли это
    слой, прежде чем тратить попытку."""
    canonical = (
        compile_text(canonical_text, registry) if canonical_text.strip() else []
    )

    progress = load_progress(raw_state, canonical_text)
    stack = build_stack(canonical, progress, registry)

    return stack[0] if stack else None