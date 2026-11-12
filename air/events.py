"""События эфира в игровом времени: окна прохождения полос, передачи станций по расписанию, ответчики.

Фонового процесса нет: наступившее выходит в эфир при приёме и скане (flush). Один выпуск на слот расписания:
после прыжка времени вперёд выходит только последний наступивший слот, после сдвига назад вышедшие не повторяются.
"""
import hashlib
import re
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from air import schedule
from air.models import Broadcast, PendingReply, Responder, ResponderFire, Transmission
from machines.access import windows
from machines.world import chrono

FADE = 10                       # минут по краям окна, где сигнал рассыпается
NOISE = "·"


def _zone(name):
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return chrono.UTC


# ---------- окна прохождения ----------

def propagation(band, game):
    """Насколько полоса проходит в игровой момент: 1 — в окне, 0 — тишина, между — края окна."""
    if band is None or not (band.window or "").strip():
        return 1.0
    try:
        rules = windows.parse(band.window)
    except windows.WindowError:
        return 1.0
    local = game.astimezone(_zone(band.time_zone))
    if windows.allows(rules, local):
        return 1.0
    for step in range(1, FADE + 1):
        if windows.allows(rules, local + timedelta(minutes=step)) or windows.allows(rules, local - timedelta(minutes=step)):
            return round(1 - step / (FADE + 1), 3)
    return 0.0


def degrade(text, quality, seed):
    """Рассыпать текст: часть знаков (не пробелов) становится «·». Одинаково для одного seed, чтобы не мигало."""
    if quality >= 1:
        return text
    loss = 1 - quality
    out = []
    for index, char in enumerate(text):
        if char.isspace():
            out.append(char)
            continue
        digest = hashlib.blake2b(f"{seed}:{index}".encode(), digest_size=2).digest()
        out.append(NOISE if int.from_bytes(digest, "big") / 65535 < loss else char)
    return "".join(out)


# ---------- передачи по расписанию ----------

def _real_moment(slot, now, game_now):
    """Когда по реальному времени был слот: назад от сейчас по нынешней скорости."""
    rate = chrono.rate_now()
    if rate <= 0 or slot >= game_now:
        return now
    return now - timedelta(seconds=(game_now - slot).total_seconds() / rate)


def flush_broadcasts(now=None):
    """Выпустить наступившие слоты. Возвращает число новых передач."""
    now = now or timezone.now()
    game_now = chrono.to_game(now)
    made = 0
    for broadcast in Broadcast.objects.filter(active=True).select_related("station"):
        try:
            lines = schedule.parse(broadcast.schedule)
        except schedule.ScheduleError:
            continue
        slot = schedule.latest(lines, game_now.astimezone(_zone(broadcast.time_zone)))
        if slot is None or not broadcast.texts:
            continue
        slot = slot.astimezone(chrono.UTC)
        if broadcast.last_slot is not None and slot <= broadcast.last_slot:
            continue
        born = chrono.to_game(broadcast.created_at)
        with transaction.atomic():
            taken = Broadcast.objects.filter(pk=broadcast.pk, last_slot=broadcast.last_slot).update(last_slot=slot, turn=broadcast.turn + 1)
            if not taken:
                continue                                    # другой запрос успел раньше
            if slot < born - timedelta(minutes=1):
                continue                                    # слот был до появления передачи: только запомнить
            text = str(broadcast.texts[broadcast.turn % len(broadcast.texts)])[:400]
            real = max(_real_moment(slot, now, game_now), now - timedelta(hours=24))
            Transmission.objects.get_or_create(broadcast=broadcast, slot=slot, defaults={
                "freq": broadcast.freq, "station": broadcast.station, "callsign": broadcast.station.name, "text": text,
                "created_at": real, "condition": broadcast.condition,
            })
            made += 1
    return made


def next_slot(broadcast, now=None):
    """Следующий выпуск (игровое UTC) для Студии или None: ищем вперёд по минуте, не дальше 8 дней."""
    try:
        lines = schedule.parse(broadcast.schedule)
    except schedule.ScheduleError:
        return None
    zone = _zone(broadcast.time_zone)
    start = chrono.to_game(now or timezone.now()).astimezone(zone).replace(second=0, microsecond=0)
    current = schedule.latest(lines, start)
    for minutes in range(1, 8 * 1440 + 1):
        moment = start + timedelta(minutes=minutes)
        found = schedule.latest(lines, moment)
        if found is not None and found != current:
            return found.astimezone(chrono.UTC)
    return None


# ---------- ответчики ----------

def _norm(text):
    return " ".join((text or "").lower().split())


def matches(responder, text):
    lines = [line.strip() for line in (responder.pattern or "").splitlines() if line.strip()]
    if responder.regex:
        for line in lines:
            try:
                if re.search(line, text, re.IGNORECASE):
                    return True
            except re.error:
                continue
        return False
    said = _norm(text)
    return any(re.search(r"(?<!\w)" + re.escape(_norm(line)) + r"(?!\w)", said) for line in lines)


def pattern_problems(pattern, regex):
    lines = [line.strip() for line in (pattern or "").splitlines() if line.strip()]
    if not lines:
        return ["Напишите хотя бы одно слово или фразу."]
    if regex:
        out = []
        for line in lines:
            try:
                re.compile(line)
            except re.error as error:
                out.append(f"«{line}»: {error}")
        return out
    return []


def react(sent, keys=frozenset(), box=None, now=None):
    """Передача игрока прозвучала: ответчики на её частоте. Возвращает эффекты хуков для браузера передавшего."""
    from secure.access import satisfied

    now = now or timezone.now()
    if sent.user_id is None:
        return []
    effects = []
    for responder in Responder.objects.filter(active=True, freq=sent.freq).select_related("station"):
        if not matches(responder, sent.text):
            continue
        if responder.condition and not satisfied(responder.condition, keys):
            continue
        recent = ResponderFire.objects.filter(responder=responder, user=sent.user, fired_at__gte=now - timedelta(minutes=responder.cooldown))
        if responder.cooldown and recent.exists():
            continue
        ResponderFire.objects.create(responder=responder, user=sent.user, fired_at=now)
        if responder.reply.strip():
            text = responder.reply.replace("{callsign}", sent.callsign).strip()[:400]
            PendingReply.objects.create(station=responder.station, freq=sent.freq, text=text, due_at=now + timedelta(seconds=responder.delay),
                                        user=sent.user if sent.sandbox else None, sandbox=sent.sandbox)
        if responder.actions and box is not None:
            from mail import talk

            effects += talk.run_actions(responder.actions, box)
    flush_replies(now)                                      # ответ без задержки выходит сразу
    return effects


def flush_replies(now=None):
    now = now or timezone.now()
    made = 0
    for reply in PendingReply.objects.filter(due_at__lte=now).select_related("station"):
        with transaction.atomic():
            if not PendingReply.objects.filter(pk=reply.pk).delete()[0]:
                continue
            Transmission.objects.create(freq=reply.freq, station=reply.station, callsign=reply.station.name, text=reply.text,
                                        created_at=reply.due_at, user=reply.user, sandbox=reply.sandbox)
            made += 1
    return made


def flush(now=None):
    """Всё наступившее в эфир: выпуски по расписанию и отложенные ответы."""
    return flush_broadcasts(now) + flush_replies(now)
