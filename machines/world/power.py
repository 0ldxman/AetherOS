"""Питание машины для сценариев: остановить, запустить, перезагрузить на N минут, обслуживание. Остановленная машина не находится
по имени (входы и мосты получают «хост не найден»), открытые на ней сессии обрываются. Перезагрузка поднимает машину сама (tick).
Обслуживание (статус Maintenance): машина в сети, но войти нельзя — игрок видит текст обслуживания; кто внутри, остаётся.
«Включена с» питание не трогает: её задают явно."""
import threading
import time
from datetime import timedelta

from django.utils import timezone

TICK = 15
_lock = threading.Lock()
_last = {"at": 0.0}


def is_down(machine):
    if not getattr(machine, "halted", False):
        return False
    return machine.halted_until is None or machine.halted_until > timezone.now()


MAINTENANCE_TEXT = "system under maintenance"


def in_maintenance(machine):
    from machines.models import Machine

    return getattr(machine, "status", "") == Machine.Status.MAINTENANCE


def maintenance_text(machine):
    return (getattr(machine, "maintenance_text", "") or "").strip() or MAINTENANCE_TEXT


def set_maintenance(machine, on, text=None, source=""):
    """Включить или снять обслуживание (text — что видит игрок; None — не менять)."""
    from machines.models import Machine

    was = in_maintenance(machine)
    fields = {"status": Machine.Status.MAINTENANCE if on else Machine.Status.ONLINE}
    if text is not None:
        fields["maintenance_text"] = text[:255]
    Machine.objects.filter(pk=machine.pk).update(**fields)
    for name, value in fields.items():
        setattr(machine, name, value)
    if on != was:
        _emit("machine.maintenance.started" if on else "machine.maintenance.ended", machine, source)


def _emit(name, machine, source):
    from engine.events import emit

    emit(name, None, machine=machine, source=source)


def set_state(machine, state, minutes=5, source="", text=""):
    """state: stop, start, reboot (стоит minutes минут, потом поднимается) или maintenance (вход закрыт, text — что видит игрок).
    start снимает и остановку, и обслуживание."""
    from machines.models import Machine, Session

    if state == "maintenance":
        set_maintenance(machine, True, text or "", source)
        return
    if state == "start":
        if in_maintenance(machine):
            set_maintenance(machine, False, source=source)
        if machine.halted:
            Machine.objects.filter(pk=machine.pk).update(halted=False, halted_until=None)
            _emit("machine.started", machine, source)
        return
    until = timezone.now() + timedelta(minutes=minutes) if state == "reboot" else None
    was_up = not is_down(machine)
    Machine.objects.filter(pk=machine.pk).update(halted=True, halted_until=until)
    Session.objects.filter(profile__machine=machine).update(kick_at=timezone.now())
    if was_up:
        _emit("machine.stopped", machine, source)


def tick(force=False):
    """Поднять машины, у которых кончилась перезагрузка."""
    from machines.models import Machine

    if not force:
        with _lock:
            if time.monotonic() - _last["at"] < TICK:
                return 0
            _last["at"] = time.monotonic()
    done = 0
    for machine in Machine.objects.filter(halted=True, halted_until__isnull=False, halted_until__lte=timezone.now()):
        Machine.objects.filter(pk=machine.pk).update(halted=False, halted_until=None)
        _emit("machine.started", machine, "перезагрузка")
        done += 1
    return done
