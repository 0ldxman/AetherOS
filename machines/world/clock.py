"""Часы машины в мире игрока: мировое время плюс сдвиг, который игрок задал командой tmset.

Сдвиг свой у каждой пары (игрок, машина). По этим часам работают окна времени входа и метки в журнале машины, поэтому сдвинуть
время значит войти вне окна или подделать след в журнале. Привилегия clock нужна, чтобы двигать часы.
"""
import math
import re
from datetime import datetime, timedelta

from django.utils import timezone

from machines.models import MachineClock

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
RELATIVE = re.compile(r"^([+-])(\d+)([smhd])$")
FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


def offset_of(machine, user):
    if user is None or machine is None:
        return 0
    return MachineClock.objects.filter(machine=machine, user=user).values_list("offset", flat=True).first() or 0


def now(machine, user=None):
    """Время на машине для этого игрока (с часовым поясом проекта)."""
    return timezone.localtime(timezone.now() + timedelta(seconds=offset_of(machine, user)))


def set_offset(machine, user, seconds):
    if seconds == 0:
        MachineClock.objects.filter(machine=machine, user=user).delete()
    else:
        MachineClock.objects.update_or_create(machine=machine, user=user, defaults={"offset": seconds})


def parse(text, machine, user):
    """Новый сдвиг в секундах по тексту команды: +3h, -1d, 2026-11-02 10:30 или reset; None, если текст не понят."""
    text = text.strip()
    if text.lower() in ("reset", "sync"):
        return 0
    found = RELATIVE.match(text.replace(" ", ""))
    if found:
        delta = int(found.group(2)) * UNITS[found.group(3)] * (1 if found.group(1) == "+" else -1)
        return offset_of(machine, user) + delta
    for fmt in FORMATS:
        try:
            wanted = timezone.make_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
        return math.ceil((wanted - timezone.now()).total_seconds())
    return None
