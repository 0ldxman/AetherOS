"""Попытка снять слой с файла игрока.

Единственная точка входа для команд терминала, которые снимают слои:

    outcome = unlock_file(view, "/home/door.bin", {"password": "hunter2"})

Вся логика в states/attempt.py, а здесь только вид машины: чтение, сохранение прогресса и применение файловых операций.
"""
import posixpath
from dataclasses import dataclass, field

from django.db import transaction

from filesystem.session_ops import OpResult, apply_file_ops
from filesystem.states.attempt import attempt_remove, fire_event
from filesystem.states.stack import RemoveResult


@dataclass
class UnlockResult:
    path: str  # путь файла после попытки (мог измениться из-за rename)
    progress: str  # прогресс игрока по слоям после попытки
    result: RemoveResult  # слой снят или нет, какой слой, что неверно
    say: list[str]  # что сказать игроку после ответа команды
    log: list[str]  # строки для журнала сессии
    ops: list[OpResult]  # что получилось с drop, rename, copy
    mail: list = field(default_factory=list)  # что получилось с письмами (mail.delivery.DeliveryResult)
    effects: list = field(default_factory=list)  # эффекты хуков для браузера (kick, alert)


def _deliver_mail(user, mails):
    """Письма из хуков: доставляются игроку (почта сама решает, что с несуществующим)."""
    from mail.delivery import deliver_by_slug

    return [deliver_by_slug(user, op.slug, delay=op.delay) for op in mails]


@transaction.atomic
def unlock_file(view, path: str, given=None) -> UnlockResult:
    """Одна попытка снять верхний слой с файла. `given` -- значения игрока (имя аргумента -> значение, типы приведены командой).

    Строка слоя игрока блокируется на время попытки: две одновременные команды иначе обе прочитали бы старые счётчики попыток и
    записали бы своё поверх."""
    entry = view.get(path)
    row = view.set_progress(path, entry.progress)                       # строка слоя есть, и её можно блокировать
    locked = type(row).objects.select_for_update(of=("self",)).get(pk=row.pk)
    view.invalidate()
    entry = view.get(path)

    outcome = attempt_remove(entry.state, locked.state, path=path, name=posixpath.basename(path), given=given)

    # Прогресс сохраняем до файловых операций: copy берёт его из записи.
    locked.state = outcome.state
    locked.save(update_fields=["state"])
    view.invalidate()

    ops = apply_file_ops(view, path, outcome.hooks.file_ops)
    final = ops[-1].path if ops and ops[-1].applied and ops[-1].op.kind == "rename" else path
    mail = _deliver_mail(view.user, outcome.hooks.mails)

    return UnlockResult(
        path=final, progress=outcome.state, result=outcome.result, say=outcome.hooks.say, log=outcome.hooks.log, ops=ops,
        mail=mail, effects=outcome.hooks.effects,
    )


@transaction.atomic
def fire_file_event(view, path: str, event: str, shown: str | None = None) -> UnlockResult | None:
    """Хуки события, которое случилось с файлом само (delete при del, restore при rcvr).

    shown это путь для {path} в текстах хуков (файл мог уже переехать). У файла без слоёв хуков нет: None."""
    entry = view.get(path)
    if entry is None or (not entry.state.strip() and not entry.progress):
        return None

    shown = shown or path
    row = view.set_progress(path, entry.progress)
    locked = type(row).objects.select_for_update(of=("self",)).get(pk=row.pk)
    view.invalidate()
    entry = view.get(path)
    fired = fire_event(entry.state, locked.state, event, path=shown, name=posixpath.basename(shown))

    locked.state = fired.state
    locked.save(update_fields=["state"])
    view.invalidate()

    ops = apply_file_ops(view, path, fired.hooks.file_ops)
    mail = _deliver_mail(view.user, fired.hooks.mails)

    return UnlockResult(
        path=path, progress=fired.state, result=RemoveResult(False), say=fired.hooks.say, log=fired.hooks.log, ops=ops, mail=mail,
        effects=fired.hooks.effects,
    )
