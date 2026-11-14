"""Моменты мира: события в игровом времени. Пока момент идёт, стоит метка world:<имя>; триггеры на неё реагируют на начало
(условие world:<имя>) и на конец (not world:<имя>).

Фонового процесса нет: tick() идёт из middleware не чаще раза в TICK секунд на процесс и из мест, где момент показывают.
Пропущенный целиком слот (никто не заходил) всё равно отрабатывает начало и конец, чтобы триггеры не потерялись.
"""
import threading
import time
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from air import schedule
from machines.world import chrono
from world import state
from world.models import WorldMoment

TICK = 15
HORIZON = timedelta(days=7)            # at показывает предстоящее на неделю вперёд по игровому времени
_last = {"at": 0.0}
_lock = threading.Lock()


def _zone(name):
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return chrono.UTC


def _lines(moment):
    try:
        return schedule.parse(moment.schedule)
    except schedule.ScheduleError:
        return []


def next_start(moment, game=None):
    """Ближайшее начало после game (игровое UTC) или None."""
    lines = _lines(moment)
    if not lines:
        return None
    found = schedule.next_after(lines, (game or chrono.game_now()).astimezone(_zone(moment.time_zone)))
    return found.astimezone(chrono.UTC) if found else None


def running(moment):
    return moment.started_at is not None and moment.ends_at is not None and moment.ends_at > chrono.game_now()


def _begin(moment, start, source):
    moment.started_at, moment.ends_at = start, start + timedelta(minutes=moment.duration)
    moment.save(update_fields=["started_at", "ends_at"])
    from engine.events import emit

    emit("moment.started", source=source, moment=moment.name, title=moment.title)
    state.set_flag(moment.name, True, source)


def _end(moment, source):
    from engine.events import emit

    emit("moment.ended", source=source, moment=moment.name, title=moment.title)
    state.set_flag(moment.name, False, source)


def tick(force=False):
    """Начать наступившие моменты и закончить истёкшие. Возвращает число изменений."""
    if not force:
        with _lock:
            if time.monotonic() - _last["at"] < TICK:
                return 0
            _last["at"] = time.monotonic()
    game = chrono.game_now()
    changed = 0
    for moment in WorldMoment.objects.filter(active=True):
        with transaction.atomic():
            moment = WorldMoment.objects.select_for_update().get(pk=moment.pk)
            flag_on = state.atom(f"world:{moment.name}")
            lines = _lines(moment)
            slot = schedule.latest(lines, game.astimezone(_zone(moment.time_zone))) if lines else None
            slot = slot.astimezone(chrono.UTC) if slot else None
            if slot is not None and (moment.started_at is None or slot > moment.started_at) \
                    and slot >= chrono.to_game(moment.created_at) - timedelta(minutes=1):    # слоты до появления момента не в счёт
                _begin(moment, slot, f"момент {moment.name}")
                changed += 1
                flag_on = True
            if flag_on and moment.ends_at is not None and moment.ends_at <= game:
                _end(moment, f"момент {moment.name}")
                changed += 1
    return changed


def start_now(moment, source):
    _begin(moment, chrono.game_now(), source)


def stop_now(moment, source):
    moment.ends_at = chrono.game_now()
    moment.save(update_fields=["ends_at"])
    _end(moment, source)


# ---------- кому виден ----------

SHOWN = ("in_list", "ticker", "toast")       # где игроки видят момент: at и {next_event}, бегущая строка, уведомление


def shown(moment):
    return [where for where in SHOWN if getattr(moment, where)]


def visible(moment, machine=None, profile=None, keys=frozenset()):
    """Виден ли момент этому игроку на этой машине хоть где-то (фильтры ОС, машин, групп и условие)."""
    from secure.access import satisfied

    if not shown(moment):
        return False
    if moment.systems and (machine is None or (machine.system or "").upper() not in {s.upper() for s in moment.systems}):
        return False
    if moment.machines and (machine is None or (machine.hostname or machine.name) not in moment.machines):
        return False
    if moment.groups:
        if profile is None:
            return False
        from machines.access.groups import principal_for

        if not set(principal_for(profile).groups) & set(moment.groups):
            return False
    return not moment.condition or satisfied(moment.condition, keys)


def board(machine=None, profile=None, keys=frozenset(), where="in_list"):
    """Что видно игроку там, где показывают where (in_list, ticker, toast или None — везде):
    [{name, title, state: live|soon|later, start, end, warn, ticker, toast}] — идущие и предстоящие в горизонте, по времени."""
    from django.db.models import Q

    tick()
    game = chrono.game_now()
    found = []
    query = Q(**{where: True}) if where else Q(in_list=True) | Q(ticker=True) | Q(toast=True)
    for moment in WorldMoment.objects.filter(query, active=True):
        if not visible(moment, machine, profile, keys):
            continue
        title = moment.title or moment.name.upper()
        extra = {"warn": moment.warn, "ticker": moment.ticker, "toast": moment.toast}
        if running(moment):
            found.append({"name": moment.name, "title": title, "state": "live", "start": moment.started_at, "end": moment.ends_at, **extra})
            continue
        start = next_start(moment, game)
        if start is None or start - game > HORIZON:
            continue
        soon = bool(moment.warn) and start - game <= timedelta(minutes=moment.warn)
        found.append({"name": moment.name, "title": title, "state": "soon" if soon else "later", "start": start,
                      "end": start + timedelta(minutes=moment.duration), **extra})
    return sorted(found, key=lambda row: (row["state"] != "live", row["start"]))


def countdown(seconds):
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    text = f"{rest // 3600:02d}:{rest % 3600 // 60:02d}:{rest % 60:02d}"
    return f"{days}d {text}" if days else text
