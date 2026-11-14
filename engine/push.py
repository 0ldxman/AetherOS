"""Очередь эффектов для браузера игрока вне запроса: окна ошибок, уведомление, бегущая строка, чёрный экран, текст и сцена в
терминале, сцена на весь экран. Действие кладёт эффект сюда, рабочий стол игрока забирает очередь опросом (desktop/push/).
Несвежие эффекты (старше KEEP) не показываются: игрок не увидит пачку окон, вернувшись через день."""
from datetime import timedelta

from django.utils import timezone

KEEP = timedelta(minutes=15)


def send(user, op, **payload):
    from engine.models import Push

    if user is None:
        return None
    return Push.objects.create(user=user, op=op[:16], payload=payload)


def take(user, limit=20):
    """Свежие эффекты игрока по порядку; забранные больше не отдаются."""
    from engine.models import Push

    if user is None or not getattr(user, "is_authenticated", False):
        return []
    now = timezone.now()
    rows = list(Push.objects.filter(user=user, taken_at__isnull=True, created_at__gte=now - KEEP).order_by("id")[:limit])
    if rows:
        Push.objects.filter(pk__in=[row.pk for row in rows]).update(taken_at=now)
    Push.objects.filter(user=user, created_at__lt=now - KEEP * 4).delete()
    return [{"op": row.op, **(row.payload or {})} for row in rows]
