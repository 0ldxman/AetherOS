"""Выполнение хуков (шаг 6, часть а): say, log, add.

Модуль ничего не знает про Django и базу. Он берёт события, которые
случились (RemoveResult.events), находит действия слоя на каждое событие
(runtime.actions_for) и выполняет их по порядку.

Что делает каждое действие:

  say   -- кладёт текст в outcome.say (его покажет терминал игроку);
  log   -- кладёт текст в outcome.log (запись в журнал сессии);
  add   -- меняет прогресс: игрок получает новый слой сверху;
  mail  -- кладёт в outcome.mails письмо, которое доставит почта (mail/delivery.py);
  kick, alert -- кладут эффект в outcome.effects: его исполняет терминал и рабочий стол;
  drop, rename, copy -- пока НЕ выполняются, а складываются в
           outcome.file_ops. Им нужны вид машины игрока и пути, это следующая часть.
"""

from dataclasses import dataclass, field
from typing import Any

from filesystem.layers.compiler import CompiledLayer, bind_params, parse_effect, parse_mail
from filesystem.layers.hooks import EFFECT_ACTIONS, MAIL_ACTIONS, PATH_ACTIONS
from filesystem.layers.parser import Action, tokenize
from filesystem.layers.registry import StateRegistry
from filesystem.layers.registry import registry as default_registry
from filesystem.layers.runtime import actions_for, layer_variables, render
from filesystem.layers.stack import Progress, RemoveResult


@dataclass(frozen=True)
class FileOp:
    """Операция над файлом, которую нужно применить позже: drop, rename, copy."""

    kind: str
    target: str


@dataclass(frozen=True)
class MailOp:
    """Письмо, которое нужно доставить игроку: идентификатор и задержка в секундах."""

    slug: str
    delay: int = 0


@dataclass
class HookOutcome:
    """Итог выполнения хуков."""

    say: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    file_ops: list[FileOp] = field(default_factory=list)
    mails: list[MailOp] = field(default_factory=list)
    effects: list[dict] = field(default_factory=list)   # что случится с игроком: kick, alert (см. hooks.EFFECT_ACTIONS)

    def extend(self, other: "HookOutcome"):
        self.say += other.say
        self.log += other.log
        self.file_ops += other.file_ops
        self.mails += other.mails
        self.effects += other.effects


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
        elif action.name in MAIL_ACTIONS:
            parsed, error = parse_mail(action)

            if error:
                raise ValueError(error)

            outcome.mails.append(MailOp(*parsed))
        elif action.name in EFFECT_ACTIONS:
            effect, error = parse_effect(action)

            if error:
                raise ValueError(error)

            outcome.effects.append(effect)
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