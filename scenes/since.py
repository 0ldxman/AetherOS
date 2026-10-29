"""Сколько времени прошло от даты до «сейчас»: для тега <since>дата | формат</since> в текстах автора.

Дата: 2027-10-29 или 2027-10-29 14:30 (UTC). «Сейчас» передаёт вызывающий (в игре это время мира, machines.World.game_now).
Форматы: days (1,112), hours, minutes, years (целые), ymd (3 y 0 mo 16 d), ago («3 min», «5 h», «2 d», «1,112 d»; будущее: «in 3 d»)."""
import calendar
import re
from datetime import datetime, timezone

FORMATS = ("days", "hours", "minutes", "years", "ymd", "ago")
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?$")


def parse_date(text):
    """Строка -> datetime (UTC) или None, если это не дата."""
    found = _DATE.match(text.strip())
    if not found:
        return None
    year, month, day, hour, minute = (int(part or 0) for part in found.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None


def _calendar_gap(start, end):
    years, months, days = end.year - start.year, end.month - start.month, end.day - start.day
    if days < 0:
        months -= 1
        previous = end.month - 1 or 12
        days += calendar.monthrange(end.year - (1 if end.month == 1 else 0), previous)[1]
    if months < 0:
        years -= 1
        months += 12
    return years, months, days


def elapsed(start, now, form="days"):
    """Текст «прошло от start до now» в заданном формате."""
    seconds = int((now - start).total_seconds())
    if form == "ago":
        wait = abs(seconds)
        if wait < 60:
            return "just now"
        text = f"{wait // 60} min" if wait < 3600 else f"{wait // 3600} h" if wait < 86400 else f"{wait // 86400:,} d"
        return text if seconds > 0 else f"in {text}"
    if form == "ymd":
        first, last = (start, now) if seconds >= 0 else (now, start)
        years, months, days = _calendar_gap(first, last)
        return f"{years} y {months} mo {days} d"
    if form == "years":
        first, last = (start, now) if seconds >= 0 else (now, start)
        return str(_calendar_gap(first, last)[0] * (1 if seconds >= 0 else -1))
    divisor = {"days": 86400, "hours": 3600, "minutes": 60}[form]
    value = seconds // divisor if seconds >= 0 else -(-seconds // divisor)
    return f"{value:,}"
