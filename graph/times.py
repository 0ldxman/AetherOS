"""Тип «Дата и время» в графе: игровой момент (мировое время, UTC). По проводу едет строкой «ГГГГ-ММ-ДД ЧЧ:ММ» (с секундами
«ЧЧ:ММ:СС», если они не ноль) — такой же, какую автор пишет в поле, поэтому поля с датой смешанные: провод даты или текст.
«сейчас» — игровое сейчас.
"""
import re
from datetime import datetime, timedelta, timezone as dt_timezone

_FORMS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d")
_CLOCK = re.compile(r"\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*")
UNITS = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}


def now():
    from machines.world import chrono

    return chrono.game_now().replace(microsecond=0)


def parse(value, words=True):
    """Игровой момент (aware UTC) из провода или текста; None — не дата. words: понимать «сейчас»."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_timezone.utc)
    text_ = str(value or "").strip()
    if words and text_.lower() in ("сейчас", "now"):
        return now()
    for form in _FORMS:
        try:
            return datetime.strptime(text_, form).replace(tzinfo=dt_timezone.utc)
        except ValueError:
            continue
    return None


def clock_full(value):
    """(час, минута, секунда) из «ЧЧ:ММ» или «ЧЧ:ММ:СС», иначе None."""
    found = _CLOCK.fullmatch(str(value or ""))
    if not found:
        return None
    hour, minute, second = int(found.group(1)), int(found.group(2)), int(found.group(3) or 0)
    return (hour, minute, second) if hour <= 23 and minute <= 59 and second <= 59 else None


def clock(value):
    found = clock_full(value)
    return found[:2] if found else None


def _hms(moment):
    return moment.strftime("%H:%M:%S" if moment.second else "%H:%M")


def text(moment):
    if moment is None:
        return ""
    moment = moment.astimezone(dt_timezone.utc)
    return f"{moment:%Y-%m-%d} {_hms(moment)}"


def of_real(real):
    """Реальный момент (из базы) как игровая дата для провода; пусто — нет момента."""
    from machines.world import chrono

    return text(chrono.to_game(real).replace(microsecond=0)) if real is not None else ""


def moment(what="datetime", source="now", value=None):
    """Нода «Время»: сейчас или заданное. what: datetime — как есть; date — та дата в 00:00; clock — это время сегодня."""
    if source != "other":
        found = now()
    elif what == "clock":
        hms = clock_full(value)
        given = parse(value) if hms is None else None
        if given is not None:
            hms = (given.hour, given.minute, given.second)
        found = now().replace(hour=hms[0], minute=hms[1], second=hms[2]) if hms else None
    else:
        found = parse(value)
    if found is not None and what == "date":
        found = found.replace(hour=0, minute=0, second=0)
    return found


def outputs(found):
    """Выходы ноды «Время»."""
    if found is None:
        return {"value": "", "date": "", "clock": "", "year": 0, "month": 0, "day": 0, "hour": 0, "minute": 0, "weekday": 0}
    found = found.astimezone(dt_timezone.utc)
    return {"value": text(found), "date": f"{found:%Y-%m-%d}", "clock": _hms(found), "year": found.year, "month": found.month, "day": found.day,
            "hour": found.hour, "minute": found.minute, "weekday": found.isoweekday()}


def shift(value, days=0, hours=0, minutes=0, seconds=0):
    found = parse(value)
    if found is None:
        return ""
    return text(found + timedelta(days=float(days or 0), hours=float(hours or 0), minutes=float(minutes or 0), seconds=float(seconds or 0)))


def diff(a, b, unit="minutes"):
    """A − B в единицах (целое, к нулю); не даты — 0."""
    first, second = parse(a), parse(b)
    if first is None or second is None:
        return 0
    return int((first - second).total_seconds() / UNITS.get(unit, 60))


def in_zone(value, zone):
    """Те же часы в поясе zone: стенные часы пояса как дата (без пояса). Нет такого пояса — пусто."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    found = parse(value)
    try:
        tz = ZoneInfo(str(zone or "").strip())
    except (ZoneInfoNotFoundError, ValueError):
        return ""
    return text(found.astimezone(tz).replace(tzinfo=dt_timezone.utc)) if found is not None else ""


def parts(value, machine=None):
    """Части момента в поясе машины (пусто — мировое время)."""
    from machines.world import chrono

    found = parse(value)
    if found is None:
        return {"year": 0, "month": 0, "day": 0, "hour": 0, "minute": 0, "weekday": 0, "date": "", "clock": ""}
    local = chrono.in_zone(found, machine) if machine is not None else found
    return {"year": local.year, "month": local.month, "day": local.day, "hour": local.hour, "minute": local.minute,
            "weekday": local.isoweekday(), "date": local.strftime("%Y-%m-%d"), "clock": local.strftime("%H:%M")}
