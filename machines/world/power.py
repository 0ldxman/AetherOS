"""Питание машины для сценариев: остановить, запустить, перезагрузить на N минут. Остановленная машина не находится по имени
(входы и мосты получают «хост не найден»), открытые на ней сессии обрываются. Перезагрузка поднимает машину сама (tick)."""
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


def _emit(name, machine, source):
    from engine.events import emit

    emit(name, None, machine=machine, source=source)


def set_state(machine, state, minutes=5, source=""):
    """state: stop, start или reboot (стоит minutes минут, потом поднимается)."""
    from machines.models import Machine, Session

    if state == "start":
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
