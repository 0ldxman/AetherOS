"""Тип «Дата и время» в графе: игровой момент (мировое время, UTC). По проводу едет строкой «ГГГГ-ММ-ДД ЧЧ:ММ» — такой же,
какую автор пишет в поле, поэтому поля с датой смешанные: провод даты или текст. «сейчас» — игровое сейчас.
"""
import re
from datetime import datetime, timedelta, timezone as dt_timezone

FORMAT = "%Y-%m-%d %H:%M"
_FORMS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
_CLOCK = re.compile(r"\s*(\d{1,2}):(\d{2})\s*")
UNITS = {"minutes": 1, "hours": 60, "days": 24 * 60}
DAY_NAMES = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def now():
    from machines.world import chrono

    return chrono.game_now()


def parse(value, words=True):
    """Игровой момент (aware UTC) из провода или текста; None — не дата. words: понимать «сейчас»."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_timezone.utc)
    text = str(value or "").strip()
    if words and text.lower() in ("сейчас", "now"):
        return now()
    for form in _FORMS:
        try:
            return datetime.strptime(text, form).replace(tzinfo=dt_timezone.utc)
        except ValueError:
            continue
    return None


def clock(value):
    """(час, минута) из «ЧЧ:ММ» или None."""
    found = _CLOCK.fullmatch(str(value or ""))
    if not found or int(found.group(1)) > 23 or int(found.group(2)) > 59:
        return None
    return int(found.group(1)), int(found.group(2))


def text(moment):
    return moment.astimezone(dt_timezone.utc).strftime(FORMAT) if moment is not None else ""


def of_real(real):
    """Реальный момент (из базы) как игровая дата для провода; пусто — нет момента."""
    from machines.world import chrono

    return text(chrono.to_game(real)) if real is not None else ""


def shift(value, amount, unit="minutes"):
    moment = parse(value)
    if moment is None:
        return ""
    return text(moment + timedelta(minutes=float(amount or 0) * UNITS.get(unit, 1)))


def diff(a, b, unit="minutes"):
    """A − B в единицах (целое, к нулю); не даты — 0."""
    first, second = parse(a), parse(b)
    if first is None or second is None:
        return 0
    return int((first - second).total_seconds() / 60 / UNITS.get(unit, 1))


def parts(value, machine=None):
    """Части момента в поясе машины (пусто — мировое время)."""
    from machines.world import chrono

    moment = parse(value)
    if moment is None:
        return {"year": 0, "month": 0, "day": 0, "hour": 0, "minute": 0, "weekday": 0, "date": "", "clock": ""}
    local = chrono.in_zone(moment, machine) if machine is not None else moment
    return {"year": local.year, "month": local.month, "day": local.day, "hour": local.hour, "minute": local.minute,
            "weekday": local.isoweekday(), "date": local.strftime("%Y-%m-%d"), "clock": local.strftime("%H:%M")}
