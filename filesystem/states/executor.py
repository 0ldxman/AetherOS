"""Выполнение хуков (шаг 6, часть а): say, log, add.

Модуль ничего не знает про Django и базу. Он берёт события, которые
случились (RemoveResult.events), находит действия слоя на каждое событие
(runtime.actions_for) и выполняет их по порядку.

Что делает каждое действие:

  say   -- кладёт текст в outcome.say (его покажет терминал игроку);
  log   -- кладёт текст в outcome.log (запись в журнал сессии);
  add   -- меняет прогресс: игрок получает новый слой сверху;
  drop, rename, copy -- пока НЕ выполняются, а складываются в
           outcome.file_ops. Им нужны SessionFile и пути, это следующая часть.
"""

from dataclasses import dataclass, field
from typing import Any

from filesystem.states.compiler import CompiledLayer, bind_params
from filesystem.states.hooks import PATH_ACTIONS
from filesystem.states.parser import Action, tokenize
from filesystem.states.registry import StateRegistry
from filesystem.states.registry import registry as default_registry
from filesystem.states.runtime import actions_for, layer_variables, render
from filesystem.states.stack import Progress, RemoveResult


@dataclass(frozen=True)
class FileOp:
    """Операция над файлом, которую нужно применить позже: drop, rename, copy."""

    kind: str
    target: str


@dataclass
class HookOutcome:
    """Итог выполнения хуков."""

    say: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    file_ops: list[FileOp] = field(default_factory=list)

    def extend(self, other: "HookOutcome"):
        self.say += other.say
        self.log += other.log
        self.file_ops += other.file_ops


def _path_of(action: Action) -> str:
    """Путь из действия. В кавычках -- как есть, иначе первое слово."""
    if action.quoted:
        return action.value

    args, _ = tokenize(action.value)
    return args[0].value


def _add_layer(
    action: Action, progress: Progress, registry: StateRegistry
) -> None:
    """add damaged / add encrypted hunter2 attempts=2: слой на верх стека."""
    args, _ = tokenize(action.value)
    cls = registry.get(args[0].value)

    if cls is None:
        raise ValueError(f"add: слоя {args[0].value!r} нет в реестре")

    params, problems = bind_params(cls, args[1:], action.line)

    if problems:
        raise ValueError("add: " + "; ".join(str(p) for p in problems))

    progress.push(cls.name, params)


def run_event(
    compiled: CompiledLayer,
    event: str,
    progress: Progress,
    variables: dict[str, Any],
    registry: StateRegistry = default_registry,
) -> HookOutcome:
    """Выполняет действия слоя на одно событие."""
    outcome = HookOutcome()

    for action in actions_for(compiled, event):
        if action.name == "say":
            outcome.say.append(render(action.value, variables))
        elif action.name == "log":
            outcome.log.append(render(action.value, variables))
        elif action.name == "add":
            _add_layer(action, progress, registry)
        elif action.name in PATH_ACTIONS:
            outcome.file_ops.append(FileOp(action.name, _path_of(action)))
        else:
            raise ValueError(f"неизвестное действие {action.name!r}")

    return outcome


def run_events(
    result: RemoveResult,
    progress: Progress,
    *,
    path: str,
    name: str,
    registry: StateRegistry = default_registry,
) -> HookOutcome:
    """Выполняет хуки по итогу попытки снять слой, события по порядку."""
    outcome = HookOutcome()

    if result.layer is None:
        return outcome

    variables = layer_variables(
        result.layer,
        path=path,
        name=name,
        attempts_left=result.attempts_left,
    )

    for event in result.events:
        outcome.extend(
            run_event(result.layer, event, progress, variables, registry)
        )

    return outcome