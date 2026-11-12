"""Расписание передач станций: разбор текста и последний наступивший слот.

Строки (любое число, слоты объединяются):
    once 2031-03-01 21:00       один раз
    daily 21:00 23:30           каждый день в эти минуты
    mon-fri 21:00               в эти дни (как в окнах входа: mon,wed,fri; sat,sun; *)
    hourly :15 :45              каждый час в эти минуты
    every 30m | every 2h        от полуночи с этим шагом
Время игровое, в поясе расписания. «#» — комментарий.
"""
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from machines.access import windows

TIME = re.compile(r"^(\d{1,2}):(\d{2})$")
MINUTE = re.compile(r"^:(\d{2})$")
EVERY = re.compile(r"^(\d+)\s*([mh])$")


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class Line:
    kind: str                   # once | days | hourly | every
    at: datetime | None = None  # once: без пояса, ставится при расчёте
    days: frozenset = frozenset()
    times: tuple = ()           # (time, ...) для days; (минута, ...) для hourly
    step: int = 0               # every: шаг в минутах


def _clock(text):
    found = TIME.match(text)
    if not found or int(found.group(1)) > 23 or int(found.group(2)) > 59:
        raise ScheduleError(f"время «{text}» не похоже на 21:00")
    return time(int(found.group(1)), int(found.group(2)))


def parse(text):
    """Список Line; ScheduleError с номером первой плохой строки."""
    lines = []
    for number, raw in enumerate((text or "").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        head, _, rest = line.partition(" ")
        head, parts = head.lower(), rest.split()
        try:
            if head == "once":
                try:
                    lines.append(Line("once", at=datetime.strptime(" ".join(parts), "%Y-%m-%d %H:%M")))
                except ValueError:
                    raise ScheduleError("после once нужна дата и время: once 2031-03-01 21:00")
            elif head == "hourly":
                minutes = []
                for part in parts:
                    found = MINUTE.match(part)
                    if not found or int(found.group(1)) > 59:
                        raise ScheduleError(f"после hourly минуты вида :15, а не «{part}»")
                    minutes.append(int(found.group(1)))
                if not minutes:
                    raise ScheduleError("после hourly нужны минуты: hourly :15")
                lines.append(Line("hourly", times=tuple(sorted(set(minutes)))))
            elif head == "every":
                found = EVERY.match("".join(parts).lower())
                if not found or int(found.group(1)) == 0:
                    raise ScheduleError("шаг вида every 30m или every 2h")
                step = int(found.group(1)) * (60 if found.group(2) == "h" else 1)
                if step > 1440:
                    raise ScheduleError("шаг every не больше суток")
                lines.append(Line("every", step=step))
            else:
                days = frozenset(range(7)) if head == "daily" else windows._days(head)
                if not parts:
                    raise ScheduleError(f"после «{head}» нужно время: {head} 21:00")
                lines.append(Line("days", days=days, times=tuple(sorted({_clock(part) for part in parts}))))
        except (ScheduleError, windows.WindowError) as error:
            raise ScheduleError(f"строка {number}: {error}")
    return lines


def problems(text):
    try:
        found = parse(text)
    except ScheduleError as error:
        return [str(error)]
    return [] if found else ["расписание пустое: напишите хотя бы daily 21:00"]


def _latest(line, now):
    zone = now.tzinfo
    if line.kind == "once":
        moment = line.at.replace(tzinfo=zone)
        return moment if moment <= now else None
    if line.kind == "hourly":
        found = [now.replace(minute=minute, second=0, microsecond=0) for minute in line.times]
        found = [moment if moment <= now else moment - timedelta(hours=1) for moment in found]
        return max(found)
    if line.kind == "every":
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        passed = int((now - midnight).total_seconds() // 60)
        return midnight + timedelta(minutes=passed - passed % line.step)
    for back in range(8):
        day = (now - timedelta(days=back)).date()
        if day.weekday() not in line.days:
            continue
        for clock in reversed(line.times):
            moment = datetime.combine(day, clock, tzinfo=zone)
            if moment <= now:
                return moment
    return None


def latest(lines, now):
    """Последний слот не позже now (aware, в поясе расписания); None, если ещё не было."""
    found = [moment for moment in (_latest(line, now) for line in lines) if moment is not None]
    return max(found) if found else None


def describe(lines):
    """Коротко для Студии: «каждый день 21:00», «по :15»."""
    out = []
    for line in lines:
        if line.kind == "once":
            out.append(f"один раз {line.at:%Y-%m-%d %H:%M}")
        elif line.kind == "hourly":
            out.append("каждый час в " + ", ".join(f":{minute:02d}" for minute in line.times))
        elif line.kind == "every":
            out.append(f"каждые {line.step} мин" if line.step % 60 else f"каждые {line.step // 60} ч")
        else:
            days = "каждый день" if len(line.days) == 7 else ",".join(windows.DAYS[day] for day in sorted(line.days))
            out.append(f"{days} в " + ", ".join(f"{clock:%H:%M}" for clock in line.times))
    return "; ".join(out)
