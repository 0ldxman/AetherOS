"""Эффективный стек файла (шаг 2, часть б).

Файл в игре = канонический стек из описания файла (Item.state)
+ прогресс игрока в сессии (PlayerFile.state, JSON):

  * added   -- слои, которые игрок добавил сам (damaged и т.п), верхний первым;
  * removed -- сколько канонических слоёв уже снято сверху;
  * attempts -- сколько неудачных попыток уже было у канонических слоёв
    (ключ -- номер слоя в каноническом стеке; у добавленных слоёв счётчик
    лежит в них самих);
  * canonical_hash -- хеш канонического текста, по которому прогресс
    считается актуальным.

Эффективный стек = added + канонические слои, кроме первых removed.
Верхний слой первым в списке: именно он отвечает на команды.

Выполнение хуков добавится следующей частью.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from collections.abc import Mapping
from typing import Any

from filesystem.layers.compiler import CompiledLayer
from filesystem.layers.parser import Layer
from filesystem.layers.registry import StateRegistry
from filesystem.layers.registry import registry as default_registry


@dataclass
class AddedLayer:
    """Слой, добавленный игроком: класс по имени и уже готовые аргументы."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0


@dataclass
class Progress:
    canonical_hash: str = ""
    removed: int = 0
    attempts: dict[str, int] = field(default_factory=dict)
    added: list[AddedLayer] = field(default_factory=list)  # верхний первым

    def push(self, name: str, params: dict[str, Any] | None = None):
        """Игрок получил новый слой сверху."""
        self.added.insert(0, AddedLayer(name, dict(params or {})))

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def load(cls, raw: str) -> "Progress":
        """Пустая строка -- чистый прогресс. Испорченный JSON даёт ошибку:
        молча терять прогресс игрока не нужно."""
        if not raw or not raw.strip():
            return cls()

        data = json.loads(raw)

        return cls(
            canonical_hash=data.get("canonical_hash", ""),
            removed=int(data.get("removed", 0)),
            attempts={
                str(key): int(value)
                for key, value in data.get("attempts", {}).items()
            },
            added=[
                AddedLayer(
                    item["name"],
                    dict(item.get("params", {})),
                    int(item.get("attempts", 0)),
                )
                for item in data.get("added", [])
            ],
        )


def canonical_hash(text: str) -> str:
    """Хеш описания файла. Концы строк и пробелы по краям не важны."""
    normalized = "\n".join(line.rstrip() for line in (text or "").strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def load_progress(raw: str, canonical_text: str) -> Progress:
    """Прогресс из PlayerFile.state. Если автор изменил описание файла,
    прогресс сбрасывается: старые счётчики к новому стеку не подходят."""
    current = canonical_hash(canonical_text)
    progress = Progress.load(raw)

    if progress.canonical_hash != current:
        return Progress(canonical_hash=current)

    return progress


def build_stack(
    canonical: list[CompiledLayer],
    progress: Progress,
    registry: StateRegistry = default_registry,
) -> list[CompiledLayer]:
    """Эффективный стек, верхний слой первым."""
    stack: list[CompiledLayer] = []

    for item in progress.added:
        cls = registry.get(item.name)

        if cls is None:
            raise ValueError(
                f"в прогрессе игрока слой {item.name!r}, которого нет в реестре"
            )

        # У добавленного игроком слоя нет текста автора: пустой узел.
        stack.append(CompiledLayer(Layer(name=item.name, line=0), cls, dict(item.params)))

    stack.extend(canonical[max(progress.removed, 0):])
    return stack


def _attempts_used(progress: Progress) -> int:
    """Неудачные попытки у верхнего слоя."""
    if progress.added:
        return progress.added[0].attempts

    return progress.attempts.get(str(progress.removed), 0)


def _set_attempts_used(progress: Progress, value: int):
    if progress.added:
        progress.added[0].attempts = value
    else:
        progress.attempts[str(progress.removed)] = value


def attempts_left(stack: list[CompiledLayer], progress: Progress) -> int | None:
    """Сколько попыток осталось у верхнего слоя (None -- без ограничения).
    Это значение подстановки {attempts_left}."""
    if not stack:
        return None

    limit = stack[0].state.max_attempts(stack[0].params)

    if limit is None:
        return None

    return max(limit - _attempts_used(progress), 0)


@dataclass
class RemoveResult:
    """Итог попытки снять верхний слой.

    removed: слой снят (прогресс уже изменён).
    layer: слой, к которому применили попытку (None -- стек пуст).
    wrong: имена снимающих аргументов, которые не названы или неверны.
    events: какие события случились, по порядку: ("remove",), ("attempt",),
        ("attempt", "fail"). Хуки по ним выполняет следующая часть.
    attempts_left: сколько попыток осталось (None -- без ограничения).
    """

    removed: bool
    layer: CompiledLayer | None = None
    wrong: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    attempts_left: int | None = None


def remove_top(
    stack: list[CompiledLayer],
    progress: Progress,
    given: Mapping[str, Any] | None = None,
) -> RemoveResult:
    """Пробует снять верхний слой значениями игрока `given` (имя -> значение,
    типы уже приведены командой). Какая именно команда это вызвала и что
    сказать игроку, решает вызывающий код (команда терминала).

    Успех: добавленный игроком слой убирается из `added`, иначе растёт
    счётчик снятых канонических слоёв.

    Неудача считается попыткой, если игрок назвал хотя бы одно из снимающих
    значений слоя (вызов вообще без них, например без пароля, попыткой не
    считается). Попытка даёт событие attempt, а когда число попыток кончается,
    ещё и fail (один раз). После этого счётчик не растёт, а снять слой
    по-прежнему можно, если не мешают другие слои сверху."""
    given = given or {}

    if not stack:
        return RemoveResult(False)

    top = stack[0]
    wrong = top.state.check_unlock(top.params, given)

    if not wrong:
        if progress.added:
            progress.added.pop(0)
        else:
            progress.attempts.pop(str(progress.removed), None)
            progress.removed += 1

        return RemoveResult(True, top, events=("remove",))

    tried = any(p.unlock and p.name in given for p in top.state.params)

    if not tried:
        return RemoveResult(False, top, wrong, attempts_left=attempts_left(stack, progress))

    events = ["attempt"]
    limit = top.state.max_attempts(top.params)

    if limit is not None:
        before = _attempts_used(progress)
        after = min(before + 1, limit)
        _set_attempts_used(progress, after)

        if before < limit <= after:
            events.append("fail")

    return RemoveResult(
        False,
        top,
        wrong,
        tuple(events),
        attempts_left(stack, progress),
    )