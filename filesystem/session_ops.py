"""Применение файловых операций хуков (drop, rename, copy) к файлам игрока.

Хуки (executor.py) только складывают операции в HookOutcome.file_ops. Здесь они выполняются над видом машины игрока
(filesystem/machine_view.py): всё идёт в слой игрока, база не меняется.

Договорённость с вызывающим кодом: перед вызовом apply_file_ops прогресс текущего файла уже сохранён, потому что copy
забирает его как есть.
"""
import posixpath
from dataclasses import dataclass

from filesystem.states.executor import FileOp


@dataclass(frozen=True)
class OpResult:
    """Что получилось с одной операцией."""

    op: FileOp
    path: str  # итоговый абсолютный путь, с которым работала операция
    applied: bool
    reason: str = ""  # если не применилась: почему


def resolve_target(current_path: str, target: str) -> str:
    """Абсолютный путь цели. `b.bin` -- рядом с текущим файлом, `/x/b.bin` -- как написано. `.` и `..` сворачиваются, выше
    корня выйти нельзя."""
    if not target.startswith("/"):
        target = posixpath.join(posixpath.dirname(current_path), target)

    return posixpath.normpath("/" + target.lstrip("/"))


def apply_file_ops(view, current_path: str, ops: list[FileOp]) -> list[OpResult]:
    """Выполняет операции по порядку над файлом по пути `current_path`. Относительные пути считаются от текущего пути файла
    (после предыдущих rename). Неприменённая операция не ломает остальные, а попадает в результат с причиной."""
    results = []
    for op in ops:
        target = resolve_target(current_path, op.target)
        found = view.get(target)

        if op.kind == "drop":
            if found is None:
                results.append(OpResult(op, target, False, "такого файла нет"))
            else:
                view.remove(target)
                results.append(OpResult(op, target, True))
            continue

        if target == current_path:
            results.append(OpResult(op, target, False, "путь тот же"))
        elif found is not None:
            results.append(OpResult(op, target, False, "путь занят"))
        elif op.kind == "rename":
            view.move(current_path, target)
            current_path = target
            results.append(OpResult(op, target, True))
        elif op.kind == "copy":
            view.copy(current_path, target)
            results.append(OpResult(op, target, True))
        else:
            raise ValueError(f"неизвестная файловая операция {op.kind!r}")
    return results
