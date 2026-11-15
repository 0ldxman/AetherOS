"""Попытка снять слой с файла игрока.

Единственная точка входа для команд терминала, которые снимают слои:

    outcome = unlock_file(view, "/home/door.bin", {"password": "hunter2"})

Вся логика в states/attempt.py, а здесь только вид машины: чтение, сохранение прогресса и применение файловых операций.
"""
import posixpath
from dataclasses import dataclass, field

from django.db import transaction

from filesystem.layers.ops import OpResult, apply_file_ops
from filesystem.layers.attempt import attempt_remove, fire_event
from filesystem.layers.stack import RemoveResult


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
    refused: str = ""  # граф попытки отказал: его текст вместо обычного «неверно»


LAYER_EVENTS = {"remove": "layer.removed", "attempt": "layer.attempt", "fail": "layer.failed"}
FILE_EVENTS = {"read": "file.read", "delete": "file.deleted", "restore": "file.restored"}


def _slug(entry):
    item = getattr(entry, "item", None)
    return getattr(item, "slug", "") or ""


def _emit(view, name, **data):
    from engine.events import emit

    emit(name, view.user, machine=view.machine, login=view.login or "", **data)


def _graph_answer(view, entry, path, raw_state, given):
    """Граф попытки слоя (у объекта): «слаг#номер» верхнего слоя игрока; у добавленного игроком слоя — только «любой слой»."""
    item = getattr(entry, "item", None)
    if item is None or not (entry.state or "").strip():
        return None
    try:
        from filesystem.layers.compiler import compile_text
        from filesystem.layers.stack import load_progress
        from graph import owned

        progress = load_progress(raw_state, entry.state)
        canonical = compile_text(entry.state)
        if progress.added:
            number, kind = "*", progress.added[0].name
        elif progress.removed < len(canonical):
            number, kind = str(progress.removed + 1), canonical[progress.removed].state.name
        else:
            return None
        values = [str(value) for value in (given or {}).values()]
        return owned.decide("layer", f"{item.slug}#{number}", view.user, host=getattr(view.machine, "hostname", "") or "", login=view.login or "",
                            item=item.slug, layer=f"{item.slug}#{number}", number=int(number) if number.isdigit() else 0, layer_type=kind,
                            given=" ".join(values), path=path)
    except Exception:                               # noqa: BLE001 — сломанный граф: слой снимается как обычно
        import logging

        logging.getLogger("graph").exception("layer attempt graph failed")
        return None


def _deliver_mail(user, mails):
    """Письма из хуков: доставляются игроку (почта сама решает, что с несуществующим)."""
    from mail.delivery import deliver_by_slug

    return [deliver_by_slug(user, op.slug, delay=op.delay) for op in mails]


@transaction.atomic
def unlock_file(view, path: str, given=None, force=False) -> UnlockResult:
    """Одна попытка снять верхний слой с файла. `given` -- значения игрока (имя аргумента -> значение, типы приведены командой).

    Строка слоя игрока блокируется на время попытки: две одновременные команды иначе обе прочитали бы старые счётчики попыток и
    записали бы своё поверх."""
    entry = view.get(path)
    row = view.set_progress(path, entry.progress)                       # строка слоя есть, и её можно блокировать
    locked = type(row).objects.select_for_update(of=("self",)).get(pk=row.pk)
    view.invalidate()
    entry = view.get(path)

    answer = None if force else _graph_answer(view, entry, path, locked.state, given)
    if answer is not None and answer["mode"] != "allow":
        return UnlockResult(path=path, progress=locked.state, result=RemoveResult(False), say=[], log=[], ops=[],
                            refused=answer["text"] or "access denied")
    outcome = attempt_remove(entry.state, locked.state, path=path, name=posixpath.basename(path), given=given, force=force or answer is not None)
    layer = outcome.result.layer.state.name if outcome.result.layer is not None else ""
    for event in outcome.result.events:
        if event in LAYER_EVENTS:
            _emit(view, LAYER_EVENTS[event], path=path, item=_slug(entry), layer=layer, wrong=list(outcome.result.wrong))

    # Прогресс сохраняем до файловых операций: copy берёт его из записи.
    locked.state = outcome.state
    locked.save(update_fields=["state"])
    view.invalidate()

    quiet = False
    hooks = outcome.hooks
    ops = [] if quiet else apply_file_ops(view, path, hooks.file_ops)
    final = ops[-1].path if ops and ops[-1].applied and ops[-1].op.kind == "rename" else path
    mail = [] if quiet else _deliver_mail(view.user, hooks.mails)

    return UnlockResult(
        path=final, progress=outcome.state, result=outcome.result, say=[] if quiet else hooks.say, log=[] if quiet else hooks.log, ops=ops,
        mail=mail, effects=[] if quiet else hooks.effects,
    )


@transaction.atomic
def fire_file_event(view, path: str, event: str, shown: str | None = None) -> UnlockResult | None:
    """Хуки события, которое случилось с файлом само (delete при del, restore при rcvr).

    shown это путь для {path} в текстах хуков (файл мог уже переехать). У файла без слоёв хуков нет: None."""
    entry = view.get(path)
    if event in FILE_EVENTS:
        _emit(view, FILE_EVENTS[event], path=shown or path, item=_slug(entry))
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

    quiet = False
    ops = [] if quiet else apply_file_ops(view, path, fired.hooks.file_ops)
    mail = [] if quiet else _deliver_mail(view.user, fired.hooks.mails)

    return UnlockResult(
        path=path, progress=fired.state, result=RemoveResult(False), say=[] if quiet else fired.hooks.say, log=[] if quiet else fired.hooks.log,
        ops=ops, mail=mail, effects=[] if quiet else fired.hooks.effects,
    )
