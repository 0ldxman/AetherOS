"""Применение файловых операций хуков к файлам сессии (шаг 6, часть б).

Хуки (executor.py) только складывают операции drop, rename и copy в
HookOutcome.file_ops. Здесь они выполняются над SessionFile.

Правило из модели: файл без записи SessionFile в сессии выглядит так, как
лежит на машине. Запись появляется, когда с файлом что-то случилось.

Договорённость с вызывающим кодом: перед вызовом apply_file_ops текущий
SessionFile уже сохранён, а его state (прогресс) уже обновлён, потому что
copy забирает state как есть.
"""

import posixpath
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from filesystem.models import MachineFile, SessionFile
from filesystem.states.executor import FileOp


@dataclass(frozen=True)
class OpResult:
    """Что получилось с одной операцией."""

    op: FileOp
    path: str  # итоговый абсолютный путь, с которым работала операция
    applied: bool
    reason: str = ""  # если не применилась: почему


def resolve_target(current_path: str, target: str) -> str:
    """Абсолютный путь цели. `b.bin` -- рядом с текущим файлом, `/x/b.bin` --
    как написано. `.` и `..` сворачиваются, выше корня выйти нельзя."""
    if not target.startswith("/"):
        target = posixpath.join(posixpath.dirname(current_path), target)

    return posixpath.normpath("/" + target.lstrip("/"))


def _find(session, path: str) -> SessionFile | None:
    """Запись сессии для файла по этому пути (может быть надгробием).

    Если записи нет, а на машине по этому пути лежит файл, который сессия
    ещё не трогала, запись создаётся. Если файл с машины уже переименован
    (запись на него есть, но под другим путём), по старому пути его нет."""
    row = SessionFile.objects.filter(session=session, path=path).first()

    if row is not None:
        return row

    machine_file = MachineFile.objects.filter(
        machine=session.profile.machine, path=path
    ).first()

    if machine_file is None:
        return None

    if SessionFile.objects.filter(session=session, file=machine_file).exists():
        return None

    return SessionFile.objects.create(session=session, file=machine_file)


def _free_target(session, path: str) -> bool:
    """Освобождает путь для rename/copy. Надгробие на этом пути стирается
    (файла там уже нет). Если там живой файл, путь занят: False."""
    row = _find(session, path)

    if row is None:
        return True

    if row.deleted_at is None:
        return False

    row.delete()
    return True


def _apply(current: SessionFile, op: FileOp) -> OpResult:
    session = current.session
    target = resolve_target(current.path, op.target)

    if op.kind == "drop":
        row = _find(session, target)

        if row is None or row.deleted_at is not None:
            return OpResult(op, target, False, "такого файла нет")

        row.deleted_at = timezone.now()
        row.save(update_fields=["deleted_at"])
        return OpResult(op, target, True)

    if target == current.path:
        return OpResult(op, target, False, "путь тот же")

    if not _free_target(session, target):
        return OpResult(op, target, False, "путь занят")

    if op.kind == "rename":
        current.path = target
        current.save(update_fields=["path"])
        return OpResult(op, target, True)

    if op.kind == "copy":
        SessionFile.objects.create(
            session=session,
            file=current.file,
            path=target,
            state=current.state,
        )
        return OpResult(op, target, True)

    raise ValueError(f"неизвестная файловая операция {op.kind!r}")


@transaction.atomic
def apply_file_ops(current: SessionFile, ops: list[FileOp]) -> list[OpResult]:
    """Выполняет операции по порядку над файлом `current`. Относительные
    пути считаются от текущего пути файла (после предыдущих rename).
    Неприменённая операция не ломает остальные, а попадает в результат
    с причиной."""
    return [_apply(current, op) for op in ops]