"""Доставка писем игроку: «mail <идентификатор> [delay=секунды]» (хук слоя), «Прислать письмо» в правилах.

Идентификатор — слаг объекта формата msg. Приходит в личный ящик игрока — его учётки на aether-main, где бы он сейчас
ни работал, сразу или через очередь. Безымянный игрок (witness) писем по триггеру не получает.
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
    """Личная учётка игрока: письма «игроку» идут сюда."""
    from machines.current import home_account
    from machines.models import Machine

    try:
        return home_account(user)
    except Machine.DoesNotExist:
        return None


def deliver_by_slug(user, slug, *, delay=0, profile=None):
    from filesystem.models import Item
    from mail.boxes import Box

    if user is None or not getattr(user, "is_authenticated", False):
        return DeliveryResult(slug, False, reason="no signed-in player")
    profile = profile or current_profile(user)
    if profile is None:
        return DeliveryResult(slug, False, reason="no account")
    delay = max(0, min(int(delay), MAX_DELAY_SECONDS))
    item = Item.objects.filter(slug=slug, format=LETTER_FORMAT).first()
    if item is None:
        return DeliveryResult(slug, False, reason=f"no letter {slug!r}")
    Box.of_profile(profile, user).queue(item, delay)
    return DeliveryResult(slug, True, immediate=delay == 0)
