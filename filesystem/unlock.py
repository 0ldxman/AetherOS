"""Попытка снять слой с файла сессии (шаг 7, часть б).

Единственная точка входа для команд терминала, которые снимают слои:

    outcome = unlock_file(session_file, {"password": "hunter2"})

Вся логика в states/attempt.py, а здесь только база: блокировка записи,
чтение, сохранение прогресса и применение файловых операций.
"""

import posixpath
from dataclasses import dataclass, field

from django.db import transaction

from filesystem.models import SessionFile
from filesystem.session_ops import OpResult, apply_file_ops
from filesystem.states.attempt import attempt_remove, fire_event
from filesystem.states.stack import RemoveResult


@dataclass
class UnlockResult:
    session_file: SessionFile  # свежая запись (путь мог измениться из-за rename)
    result: RemoveResult  # слой снят или нет, какой слой, что неверно
    say: list[str]  # что сказать игроку после ответа команды
    log: list[str]  # строки для журнала сессии
    ops: list[OpResult]  # что получилось с drop, rename, copy
    mail: list = field(default_factory=list)  # что получилось с письмами (mail.delivery.DeliveryResult)
    effects: list = field(default_factory=list)  # эффекты хуков для браузера (kick, alert)


def _deliver_mail(user, mails):
    """Письма из хуков: доставляются игроку сессии (почта сама решает, что с несуществующим)."""
    from mail.delivery import deliver_by_slug

    return [deliver_by_slug(user, op.slug, delay=op.delay) for op in mails]


@transaction.atomic
def unlock_file(session_file: SessionFile, given=None) -> UnlockResult:
    """Одна попытка снять верхний слой с файла. `given` -- значения игрока
    (имя аргумента -> значение, типы уже приведены командой).

    Запись блокируется на время попытки: две одновременные команды иначе
    обе прочитали бы старые счётчики попыток и записали бы своё поверх.
    Удалённый файл (deleted_at) сюда передавать не нужно, это дело команды."""
    locked = (
        SessionFile.objects.select_for_update(of=("self",))
        .select_related("file", "session__profile__machine")
        .get(pk=session_file.pk)
    )

    outcome = attempt_remove(
        locked.file.state,
        locked.state,
        path=locked.path,
        name=posixpath.basename(locked.path),
        given=given,
    )

    # Прогресс сохраняем до файловых операций: copy берёт state из записи.
    locked.state = outcome.state
    locked.save(update_fields=["state"])

    ops = apply_file_ops(locked, outcome.hooks.file_ops)
    mail = _deliver_mail(locked.session.user, outcome.hooks.mails)

    return UnlockResult(
        session_file=locked,
        result=outcome.result,
        say=outcome.hooks.say,
        log=outcome.hooks.log,
        ops=ops,
        mail=mail,
        effects=outcome.hooks.effects,
    )


@transaction.atomic
def fire_file_event(session_file: SessionFile, event: str, path: str | None = None) -> UnlockResult | None:
    """Хуки события, которое случилось с файлом сессии само (delete при del, restore при rcvr).

    path это путь для {path} в текстах хуков (файл мог уже переехать). У файла без слоёв хуков нет: None."""
    if not session_file.file.state.strip() and not session_file.state:
        return None

    locked = (
        SessionFile.objects.select_for_update(of=("self",))
        .select_related("file", "session__profile__machine")
        .get(pk=session_file.pk)
    )
    shown = path or locked.path
    fired = fire_event(locked.file.state, locked.state, event, path=shown, name=posixpath.basename(shown))

    locked.state = fired.state
    locked.save(update_fields=["state"])

    ops = apply_file_ops(locked, fired.hooks.file_ops)
    mail = _deliver_mail(locked.session.user, fired.hooks.mails)

    return UnlockResult(
        session_file=locked,
        result=RemoveResult(False),
        say=fired.hooks.say,
        log=fired.hooks.log,
        ops=ops,
        mail=mail,
        effects=fired.hooks.effects,
    )
