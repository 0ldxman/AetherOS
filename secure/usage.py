"""Где используется ключ во всём проекте.

Условия по ключам живут в разных местах: вики (записи и разделы), приложения
и профили машин, ключи файлов. Админка ключей и сводка автора берут общий
ответ отсюда, чтобы «ключ нигде не используется» было правдой.
"""
from dataclasses import dataclass

from django.urls import reverse

from secure.access import condition_slugs


@dataclass(frozen=True)
class Usage:
    kind: str    # "запись", "раздел", "приложение", "профиль", "объект", "письмо"
    label: str
    url: str


_providers = []


def register(usage, conditions=None):
    """Приложение называет свои места с ключами. Так secure не знает ни вики, ни почты.

    usage(slug) -> [Usage]: где ключ назван; conditions() -> [условие]: все его JSON-условия (для списка занятых ключей).
    """
    _providers.append((usage, conditions))


def _profiles(slug):
    from machines.models import MachineProfile

    return [
        Usage("профиль", str(profile), reverse("admin:machines_machineprofile_change", args=[profile.pk]))
        for profile in MachineProfile.objects.select_related("machine").exclude(key_condition=None)
        if slug in condition_slugs(profile.key_condition)
    ]


def key_usage(slug):
    """Список Usage для ключа: вики, машины, файлы."""
    from filesystem.models import Item, ItemKey, ItemSignature, Placement, Volume

    found = _profiles(slug)
    for usage, _ in _providers:
        found += usage(slug)
    for link in ItemKey.objects.filter(key__slug=slug).select_related("item"):
        found.append(Usage("объект", str(link.item), reverse("admin:filesystem_item_change", args=[link.item_id])))
    for link in ItemSignature.objects.filter(key__slug=slug).select_related("item"):
        found.append(Usage("подпись", str(link.item), reverse("admin:filesystem_item_change", args=[link.item_id])))
    for model, kind, admin_name in ((Item, "объект", "item"), (Placement, "размещение", "placement"), (Volume, "том", "volume")):
        for obj in model.objects.exclude(access={}):
            if slug in condition_slugs(obj.access):
                found.append(Usage(kind, str(obj), reverse(f"admin:filesystem_{admin_name}_change", args=[obj.pk])))
    return found


def used_slugs():
    """Множество slug'ов ключей, встречающихся вне вики (машины и файлы)."""
    from filesystem.models import Item, ItemKey, ItemSignature, Placement, Volume

    slugs = set()
    from machines.models import MachineProfile

    for condition in MachineProfile.objects.exclude(key_condition=None).values_list("key_condition", flat=True):
        slugs.update(condition_slugs(condition))
    for _, conditions in _providers:
        for condition in conditions() if conditions else ():
            slugs.update(condition_slugs(condition))
    slugs.update(ItemKey.objects.values_list("key__slug", flat=True))
    slugs.update(ItemSignature.objects.values_list("key__slug", flat=True))
    for model in (Item, Placement, Volume):
        for access in model.objects.exclude(access={}).values_list("access", flat=True):
            slugs.update(condition_slugs(access))
    return slugs
