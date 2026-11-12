"""Игровое время: опорные точки «реальный момент ↔ игровой момент» со скоростью хода.

Игровое время в реальный момент t = игровой момент последней наступившей точки + (t − её реальный момент) × её скорость.
Скорость любая неотрицательная: 1 — время идёт как в жизни, 0 — стоит, 0.5 — вдвое медленнее, 24 — сутки за час.
Новая точка с игровой датой больше нынешней — прыжок вперёд, меньше — назад.

Хранение: моменты в базе (created_at и подобные) остаются реальным UTC и переводятся в игровое время при показе по точке,
действовавшей тогда (to_game). Поэтому записи переживают любые сдвиги: наступившие точки не правятся, только добавляются новые.
Поля, где лежит уже игровой момент (LoginEvent.shown_at, MailMark.arrived_at, Machine.booted_at), показываются как есть.

Пока точек нет, время стоит на dates.GAME_NOW (так было до появления точек, на этом держатся тесты).
Часовой пояс у каждой машины свой (Machine.time_zone): игровое время одно, показ в поясе машины.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from django.utils import timezone

from machines import memo
from machines.world import dates

UTC = dt_timezone.utc


@dataclass(frozen=True)
class Anchor:
    real_at: datetime
    game_at: datetime
    rate: float
    pk: int | None = None
    note: str = ""

    def game(self, real):
        return self.game_at + timedelta(seconds=(real - self.real_at).total_seconds() * self.rate)


FROZEN = Anchor(datetime(2000, 1, 1, tzinfo=UTC), dates.GAME_NOW, 0.0)


def _load():
    from machines.models import TimeAnchor

    rows = [Anchor(row.real_at, row.game_at, float(row.rate), row.pk, row.note) for row in TimeAnchor.objects.order_by("real_at", "pk")]
    return rows or [FROZEN]


def anchors():
    """Точки по реальному времени; без точек одна условная «стоит на GAME_NOW». Читается раз за запрос."""
    return memo.cached(("time-anchors",), _load)


def _index(real, rows):
    found = 0
    for number, row in enumerate(rows):
        if row.real_at <= real:
            found = number
        else:
            break
    return found


def anchor_at(real):
    """Точка, действующая в реальный момент (до первой точки действует первая: время продолжается назад по её скорости)."""
    rows = anchors()
    return rows[_index(real, rows)]


def to_game(real):
    """Игровой момент (UTC) для реального момента."""
    return anchor_at(real).game(real)


def game_now():
    return to_game(timezone.now())


def rate_now():
    return anchor_at(timezone.now()).rate


def to_real(game, after=None):
    """Первый реальный момент не раньше after (по умолчанию сейчас), когда игровое время дойдёт до game; None, если не дойдёт.

    Прыжок вперёд через game засчитывается в момент прыжка. Если игровое время уже позади game, ответ — after."""
    after = after or timezone.now()
    rows = anchors()
    first = _index(after, rows)
    for number in range(first, len(rows)):
        row = rows[number]
        begin = max(row.real_at, after) if number == first else row.real_at
        end = rows[number + 1].real_at if number + 1 < len(rows) else None
        if row.game(begin) >= game:
            return begin
        if row.rate > 0:
            reach = row.real_at + timedelta(seconds=(game - row.game_at).total_seconds() / row.rate)
            if end is None or reach < end:
                return max(reach, begin)
    return None


def next_change(after=None):
    """Ближайшая будущая точка (для часов в браузере) или None."""
    after = after or timezone.now()
    return next((row for row in anchors() if row.real_at > after), None)


# ---------- часовые пояса машин ----------

def valid_zone(name):
    return name in _zones()


def _zones():
    return memo.cached(("time-zones",), available_timezones)


def zone(machine=None):
    name = getattr(machine, "time_zone", "") or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def local(real, machine=None):
    """Реальный момент как игровое время в поясе машины."""
    return to_game(real).astimezone(zone(machine))


def in_zone(game, machine=None):
    """Уже игровой момент (shown_at, arrived_at) в поясе машины."""
    return game.astimezone(zone(machine))


def stamp(real, machine=None, fmt="%Y-%m-%d %H:%M"):
    return local(real, machine).strftime(fmt)


def client(machine=None, user=None):
    """Часы для браузера: игровое «сейчас» машины, скорость и ближайшая смена хода. Время в миллисекундах эпохи."""
    from machines.world.clock import offset_of

    real = timezone.now()
    shift = timedelta(seconds=offset_of(machine, user))
    found = next_change(real)
    ms = lambda moment: int(moment.timestamp() * 1000)     # noqa: E731
    return {
        "real": ms(real), "game": ms(to_game(real) + shift), "rate": anchor_at(real).rate,
        "zone": str(zone(machine)), "offset_min": int(local(real, machine).utcoffset().total_seconds() // 60),
        "next": {"real": ms(found.real_at), "game": ms(found.game_at + shift), "rate": found.rate} if found else None,
    }


# ---------- Студия: правка точек ----------

def later_than_now(game, after=None):
    """Сколько записей окажется «в будущем», если игровое «сейчас» станет game: {что: сколько}. Для предупреждения о сдвиге назад."""
    from mail.models import MailMark
    from machines.models import LoginEvent

    after = after or timezone.now()
    found = {}
    shown = LoginEvent.objects.filter(shown_at__gt=game).count()
    if shown:
        found["записей журнала входов"] = shown
    letters = MailMark.objects.filter(arrived_at__gt=game).count()
    if letters:
        found["писем"] = letters
    real_since = to_real(game, after=datetime(1970, 1, 1, tzinfo=UTC))
    if real_since is not None and real_since < after:
        from air.models import Transmission

        sent = Transmission.objects.filter(created_at__gt=real_since).count()
        if sent:
            found["передач в эфире"] = sent
    return found


class TimeError(ValueError):
    """Отказ в правке точек времени: текст для автора."""


GRACE = timedelta(seconds=30)        # точку «сейчас» с часов браузера принимаем, даже если она чуть в прошлом


def _check(real_at, game_at, rate, now, skip=None):
    from machines.models import TimeAnchor

    if real_at < now - GRACE:
        raise TimeError("Точка в прошлом: наступившее время не переписывается. Добавьте точку на сейчас или позже.")
    if rate < 0:
        raise TimeError("Скорость не может быть отрицательной.")
    if TimeAnchor.objects.filter(real_at=max(real_at, now)).exclude(pk=skip).exists():
        raise TimeError("На этот реальный момент уже есть точка.")
    if game_at.year < 1900 or game_at.year > 2200:
        raise TimeError("Игровая дата вне 1900–2200.")


def add(real_at, game_at, rate=1, note="", now=None):
    """Новая точка; real_at=None — сейчас. TimeError, если точка в прошлом."""
    from machines.models import TimeAnchor

    now = now or timezone.now()
    real_at = real_at or now
    _check(real_at, game_at, float(rate), now)
    anchor = TimeAnchor.objects.create(real_at=max(real_at, now), game_at=game_at, rate=rate, note=note[:200])
    forget()
    return anchor


def change(anchor, real_at, game_at, rate, note="", now=None):
    now = now or timezone.now()
    if anchor.real_at <= now:
        raise TimeError("Точка уже наступила: её не правят. Добавьте новую.")
    _check(real_at, game_at, float(rate), now, skip=anchor.pk)
    anchor.real_at, anchor.game_at, anchor.rate, anchor.note = max(real_at, now), game_at, rate, note[:200]
    anchor.save()
    forget()
    return anchor


def remove(anchor, now=None):
    if anchor.real_at <= (now or timezone.now()):
        raise TimeError("Точка уже наступила: её не удаляют. Добавьте новую.")
    anchor.delete()
    forget()


def _span(seconds):
    seconds = abs(int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    parts = [f"{days} д"] if days else []
    if hours:
        parts.append(f"{hours} ч")
    if not days and rest // 60:
        parts.append(f"{rest // 60} мин")
    return " ".join(parts) or "меньше минуты"


def game_before(real_at, skip=None):
    """Каким было бы игровое время в real_at без точки skip (для правки будущей точки и предупреждений)."""
    rows = [row for row in anchors() if row.pk != skip] or [FROZEN]
    return rows[_index(real_at, rows)].game(real_at)


def forget():
    """После правки точек: в этом запросе читать их заново."""
    memo.forget(("time-anchors",))


def warnings(real_at, game_at, now=None, skip=None):
    """Что заметит мир, если в real_at игровое время станет game_at: сдвиг назад и записи, которые окажутся позже нового «сейчас»."""
    now = now or timezone.now()
    real_at = max(real_at or now, now)
    before = game_before(real_at, skip)
    found = []
    if game_at < before - timedelta(minutes=1):
        found.append(f"Сдвиг назад на {_span((before - game_at).total_seconds())}: игровое время пойдёт заново с {game_at:%Y-%m-%d %H:%M} UTC.")
        found += [f"{count} {what} окажутся позже нового «сейчас»." for what, count in later_than_now(game_at, now).items()]
    return found
