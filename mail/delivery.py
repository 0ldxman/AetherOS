"""Доставка писем по хуку слоя: «mail <идентификатор> [delay=секунды]» кладёт письмо в ящик учётки игрока.

Письмо это объект формата msg с этим слагом. Приходит в ящик учётки, под которой игрок сейчас работает (последняя
сессия), сразу или через очередь. Безымянный игрок (witness) писем по триггеру не получает.
"""
from dataclasses import dataclass

MAX_DELAY_SECONDS = 7 * 24 * 3600
LETTER_FORMAT = "msg"


@dataclass(frozen=True)
class DeliveryResult:
    slug: str
    delivered: bool          # письмо поставлено игроку (или уже было)
    immediate: bool = False  # оно сразу видно (без задержки)
    reason: str = ""         # если не доставлено: почему


def current_profile(user):
    """Учётка, под которой игрок работал последней."""
    from machines.models import Session

    session = Session.objects.filter(user=user).select_related("profile__machine").order_by("-seen_at", "-pk").first()
    return session.profile if session is not None else None


def deliver_by_slug(user, slug, *, delay=0, profile=None):
    from filesystem.models import Item
    from mail.boxes import Box

    if user is None or not getattr(user, "is_authenticated", False):
        return DeliveryResult(slug, False, reason="no signed-in player")
    item = Item.objects.filter(slug=slug, format=LETTER_FORMAT).first()
    if item is None:
        return DeliveryResult(slug, False, reason=f"no letter {slug!r}")
    profile = profile or current_profile(user)
    if profile is None:
        return DeliveryResult(slug, False, reason="no account")
    delay = max(0, min(int(delay), MAX_DELAY_SECONDS))
    Box.of_profile(profile, user).queue(item, delay)
    return DeliveryResult(slug, True, immediate=delay == 0)
