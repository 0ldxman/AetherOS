"""Очередь эффектов для браузера игрока вне запроса: окна ошибок, уведомление, бегущая строка, чёрный экран, текст и сцена в
терминале, сцена на весь экран. Действие кладёт эффект сюда, рабочий стол игрока забирает очередь опросом (desktop/push/).
Несвежие эффекты (старше KEEP) не показываются: игрок не увидит пачку окон, вернувшись через день.

«Где» (account:<номер>, machine:<номер>): эффект для учётки или машины ждёт, пока стол игрока (терминальный — его терминал) окажется
там; не дождался за KEEP — устарел."""
from datetime import timedelta

from django.utils import timezone

KEEP = timedelta(minutes=15)


TERMINAL = {"terminal", "tscene"}            # эффекты терминала: «где» сверяется с его сессией, остальные — со столом


def where_of(profile=None, machine=None):
    if profile is not None:
        return f"account:{profile.pk}"
    return f"machine:{machine.pk}" if machine is not None else ""


def send(user, op, where="", **payload):
    from engine.models import Push

    if user is None:
        return None
    return Push.objects.create(user=user, op=op[:16], payload=payload, where=where or "")


def _here(where, profile):
    if not where:
        return True
    if profile is None:
        return False
    kind, _, pk = where.partition(":")
    return str(profile.pk if kind == "account" else profile.machine_id) == pk


def take(user, limit=20, desk=None, terminal=None):
    """Свежие эффекты игрока по порядку; забранные больше не отдаются. desk и terminal — учётки, где сейчас его стол и терминал:
    эффект с «где» отдаётся, только когда игрок там (иначе ждёт)."""
    from engine.models import Push

    if user is None or not getattr(user, "is_authenticated", False):
        return []
    now = timezone.now()
    fresh = Push.objects.filter(user=user, taken_at__isnull=True, created_at__gte=now - KEEP).order_by("id")
    rows = [row for row in fresh if _here(row.where, terminal if row.op in TERMINAL else desk)][:limit]
    if rows:
        Push.objects.filter(pk__in=[row.pk for row in rows]).update(taken_at=now)
    Push.objects.filter(user=user, created_at__lt=now - KEEP * 4).delete()
    return [{"op": row.op, **(row.payload or {})} for row in rows]
