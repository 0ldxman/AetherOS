"""Чистка растущих служебных таблиц: забытые эффекты стола (Push) и старый журнал мира (WorldEvent). Раз в час на процесс.

События игрока (engine.Event), проходы нод (Hit) и прохождения (Run) не трогаются: из них «уже было», воронка и журнал сценария."""
import threading
import time
from datetime import timedelta

from django.utils import timezone

TICK = 3600
WORLD_EVENTS = timedelta(days=30)
_last = {"at": 0.0}
_lock = threading.Lock()


def sweep(now=None):
    """Удалить устаревшее. Возвращает {таблица: сколько удалено}."""
    from engine import push
    from engine.models import Push
    from world.models import WorldEvent

    now = now or timezone.now()
    return {
        "push": Push.objects.filter(created_at__lt=now - push.KEEP * 4).delete()[0],
        "world_events": WorldEvent.objects.filter(at__lt=now - WORLD_EVENTS).delete()[0],
    }


def tick(force=False):
    if not force:
        with _lock:
            if time.monotonic() - _last["at"] < TICK:
                return None
            _last["at"] = time.monotonic()
    return sweep()
