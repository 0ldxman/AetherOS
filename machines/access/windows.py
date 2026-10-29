"""Окна времени входа: разбор текста и проверка момента.

Строка окна: ``дни: интервал интервал...`` или ``except дни: интервал...``. Дни: ``mon-fri``, ``mon,wed,fri``, ``sat,sun``, ``*``
(каждый день). Интервал: ``9:00-13:00``, часы без ведущего нуля; ``*`` вместо интервалов значит весь день. Интервал через полночь
(``22:00-6:00``) относится к дню, в который он начался. Вход разрешён, если подходит хотя бы одна обычная строка и не подходит ни одна
строка except; без обычных строк разрешено всё, кроме except. Пустой текст не ограничивает.
"""
import re
from dataclasses import dataclass

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


class WindowError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    exclude: bool
    days: frozenset
    spans: tuple            # ((с минуты суток, по минуту суток), ...); конец меньше начала: через полночь


def _days(text):
    found = set()
    for part in text.split(","):
        part = part.strip().lower()
        if part == "*":
            found |= set(range(7))
        elif "-" in part:
            first, _, last = part.partition("-")
            if first not in DAYS or last not in DAYS:
                raise WindowError(f"неизвестный день «{part}»")
            start, end = DAYS.index(first), DAYS.index(last)
            found |= {(start + step) % 7 for step in range(((end - start) % 7) + 1)}
        elif part in DAYS:
            found.add(DAYS.index(part))
        else:
            raise WindowError(f"неизвестный день «{part}»")
    if not found:
        raise WindowError("не указаны дни")
    return frozenset(found)


def _minute(text):
    found = TIME.match(text)
    if not found or int(found.group(1)) > 24 or int(found.group(2)) > 59:
        raise WindowError(f"время «{text}» не похоже на 9:00")
    return int(found.group(1)) * 60 + int(found.group(2))


def parse(text):
    """Список Rule из текста; WindowError с описанием первой плохой строки."""
    rules = []
    for number, line in enumerate((text or "").splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        exclude = line.lower().startswith("except ")
        body = line[7:].strip() if exclude else line
        days, colon, rest = body.partition(":")
        if not colon or not rest.strip():
            raise WindowError(f"строка {number}: нужно «дни: интервалы»")
        try:
            spans = ((0, 1440),) if rest.strip() == "*" else tuple(
                (_minute(first), _minute(last)) for first, _, last in (item.partition("-") for item in rest.split())
            )
            rules.append(Rule(exclude, _days(days), spans))
        except WindowError as error:
            raise WindowError(f"строка {number}: {error}")
    return rules


def _inside(rule, weekday, minute):
    for start, end in rule.spans:
        if start <= end:
            if weekday in rule.days and start <= minute < end:
                return True
        elif (weekday in rule.days and minute >= start) or ((weekday - 1) % 7 in rule.days and minute < end):
            return True
    return False


def allows(rules, moment):
    """Пускают ли окна в этот момент (datetime)."""
    if not rules:
        return True
    weekday, minute = moment.weekday(), moment.hour * 60 + moment.minute
    if any(_inside(rule, weekday, minute) for rule in rules if rule.exclude):
        return False
    allowed = [rule for rule in rules if not rule.exclude]
    return not allowed or any(_inside(rule, weekday, minute) for rule in allowed)


def week(rules, step=30):
    """Неделя для показа: 7 дней (пн..вс) × отрезки по step минут, можно ли войти в середине отрезка."""
    from datetime import datetime, timedelta

    monday = datetime(2026, 11, 2)                                # любой понедельник: важны только день недели и время
    slots = 24 * 60 // step
    return [[allows(rules, monday + timedelta(days=day, minutes=step * slot + step // 2)) for slot in range(slots)] for day in range(7)]
