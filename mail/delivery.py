"""Доставка писем по триггеру: хук «mail <slug> [delay=секунды]» кладёт письмо игроку.

Письмо с идентификатором (slug) не видно никому, пока его не доставили. Доставка это запись
(письмо, игрок, время, когда оно появится). Повторная доставка того же письма тому же игроку
ничего не меняет. Безымянный игрок (witness) не решает загадки и писем по триггеру не получает.
"""
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from .models import Delivered, Message

MAX_DELAY_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True)
class DeliveryResult:
    slug: str
    delivered: bool          # письмо поставлено в очередь этому игроку (или уже было)
    immediate: bool = False  # оно сразу видно (без задержки)
    reason: str = ""         # если не доставлено: почему


def deliver(user, message, *, delay=0, now=None):
    """Доставить письмо игроку. Возвращает (Delivered, создана ли запись)."""
    if user is None or not getattr(user, "is_authenticated", False):
        raise ValueError("письма по триггеру получают только вошедшие игроки")

    delay = max(0, min(int(delay), MAX_DELAY_SECONDS))
    now = now or timezone.now()

    return Delivered.objects.get_or_create(
        message=message,
        user=user,
        defaults={"available_at": now + timedelta(seconds=delay)},
    )


def deliver_by_slug(user, slug, *, delay=0, now=None):
    """То же по идентификатору письма (так его называет хук)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return DeliveryResult(slug, False, reason="no signed-in player")

    message = Message.objects.filter(slug=slug).first()

    if message is None:
        return DeliveryResult(slug, False, reason=f"no letter {slug!r}")

    record, created = deliver(user, message, delay=delay, now=now)
    immediate = record.available_at <= (now or timezone.now())
    return DeliveryResult(slug, True, immediate=immediate)
