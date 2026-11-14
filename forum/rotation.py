"""Ротация тем форума по игровому времени: закрытые уходят в архив, неактивные предупреждаются и закрываются, длинные делятся на тома,
старый архив по желанию сжимается. Настройки у пространства, раздел переопределяет любой ключ (ключа нет: как выше). tick() из world/middleware.

Ключи (числа, 0: выключено): archive_days — через сколько игровых дней закрытая тема уходит в архив; idle_days — сколько дней тишины до
предупреждения; grace_days — сколько дней после предупреждения до закрытия; volume_posts — при скольких сообщениях тема закрывается томом и
продолжается следующим; compress_days — через сколько дней в архиве от темы остаются заголовок и первое сообщение.
"""
import threading
import time

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from forum.models import Kind, Post, Topic

DEFAULTS = {"archive_days": 7, "idle_days": 14, "grace_days": 3, "volume_posts": 200, "compress_days": 0}
LIMITS = {"archive_days": 3650, "idle_days": 3650, "grace_days": 3650, "volume_posts": 100000, "compress_days": 3650}
SYSTEM = "SYS"
TICK = 60
_lock = threading.Lock()
_last = {"at": 0.0}


class RotationError(ValueError):
    pass


def clean(data):
    """Проверенные настройки ротации: только известные ключи, целые от 0; None и пустое выкидываются (как выше)."""
    if not data:
        return {}
    if not isinstance(data, dict):
        raise RotationError("ротация: ожидается словарь")
    out = {}
    for key, value in data.items():
        if key not in DEFAULTS:
            raise RotationError(f"ротация: неизвестный ключ «{key}»")
        if value is None or value == "":
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise RotationError(f"ротация: «{key}» должно быть числом") from None
        if not 0 <= number <= LIMITS[key]:
            raise RotationError(f"ротация: «{key}» от 0 до {LIMITS[key]}")
        out[key] = number
    return out


def settings_for(section):
    """Действующие настройки раздела: умолчания ← пространство ← разделы от корня."""
    from forum.logic import _chain

    found = dict(DEFAULTS)
    found.update(section.space.rotation or {})
    for item in _chain(section):
        found.update(item.rotation or {})
    return found


def _days(since):
    """Сколько игровых дней прошло с реального момента since."""
    from machines.world import chrono

    return (chrono.game_now() - chrono.to_game(since)).total_seconds() / 86400


def _system_post(topic, text):
    """Служебная запись системы: не поднимает тему и не сбрасывает предупреждение."""
    root = topic.posts.filter(root=True).first()
    return Post.objects.create(topic=topic, parent=root, name=SYSTEM, kind=Kind.SYSTEM, text=text)


def exempt_idle(topic):
    """Закреплённые темы и темы системы или персонажа не закрываются по тишине (только томами)."""
    return topic.pinned or topic.kind != Kind.PLAYER


def close(topic, reason):
    now = timezone.now()
    Topic.objects.filter(pk=topic.pk).update(locked=True, closed_at=now, closed_reason=reason, warned_at=None)
    topic.locked, topic.closed_at, topic.closed_reason, topic.warned_at = True, now, reason, None


def reopen(topic):
    Topic.objects.filter(pk=topic.pk).update(locked=False, closed_at=None, closed_reason="", warned_at=None, archived_at=None, compressed=False)


def full(topic, rules=None):
    rules = rules or settings_for(topic.section)
    limit = rules["volume_posts"]
    return bool(limit) and topic.posts.count() >= limit


@transaction.atomic
def next_volume(topic):
    """Закрыть тему томом и открыть следующий с тем же заголовком и автором. Возвращает новый том."""
    number = topic.volume or 1
    if not topic.volume:
        Topic.objects.filter(pk=topic.pk).update(volume=1)
        topic.volume = 1
    _system_post(topic, f"Volume {number} is full. Continued in volume {number + 1}.")
    close(topic, "volume")
    fresh = Topic.objects.create(section=topic.section, title=topic.title, author=topic.author, name=topic.name, kind=topic.kind,
                                 character=topic.character, pinned=topic.pinned, volume=number + 1, prev=topic)
    Post.objects.create(topic=fresh, root=True, author=topic.author, name=topic.name, kind=topic.kind, character=topic.character,
                        text=f"Volume {number + 1}. Continued from volume {number}.", created_at=fresh.created_at)
    return fresh


def _step(topic, rules):
    """Одна тема: что с ней пора сделать. Возвращает True, если что-то изменилось."""
    if topic.archived_at is not None:
        if rules["compress_days"] and not topic.compressed and _days(topic.archived_at) >= rules["compress_days"]:
            Topic.objects.filter(pk=topic.pk).update(compressed=True)
            return True
        return False
    if topic.locked:
        if topic.closed_at is None:                         # закрыта до появления ротации или напрямую: отсчёт с этой минуты
            Topic.objects.filter(pk=topic.pk).update(closed_at=timezone.now(), closed_reason=topic.closed_reason or "manual")
            return True
        if rules["archive_days"] and _days(topic.closed_at) >= rules["archive_days"]:
            Topic.objects.filter(pk=topic.pk).update(archived_at=timezone.now())
            return True
        return False
    if rules["volume_posts"] and topic.total >= rules["volume_posts"]:
        next_volume(topic)
        return True
    if exempt_idle(topic) or not rules["idle_days"]:
        return False
    if topic.warned_at is None:
        if _days(topic.bumped_at) >= rules["idle_days"]:
            grace = rules["grace_days"]
            _system_post(topic, f"No activity for {rules['idle_days']} days. This topic will be closed in {grace} days unless someone posts."
                         if grace else f"No activity for {rules['idle_days']} days. This topic is closed.")
            if grace:
                Topic.objects.filter(pk=topic.pk).update(warned_at=timezone.now())
            else:
                close(topic, "idle")
            return True
        return False
    if _days(topic.warned_at) >= rules["grace_days"]:
        _system_post(topic, "Closed for inactivity.")
        close(topic, "idle")
        return True
    return False


def tick(force=False):
    """Пройти все живые темы. Не чаще раза в TICK секунд на процесс. Возвращает число изменённых тем."""
    if not force:
        with _lock:
            if time.monotonic() - _last["at"] < TICK:
                return 0
            _last["at"] = time.monotonic()
    rules, changed = {}, 0
    topics = (Topic.objects.filter(hidden_at__isnull=True, compressed=False, section__archived=False)
              .select_related("section__space", "section__parent").annotate(total=Count("posts")))
    for topic in topics:
        if topic.section_id not in rules:
            rules[topic.section_id] = settings_for(topic.section)
        if _step(topic, rules[topic.section_id]):
            changed += 1
    return changed
