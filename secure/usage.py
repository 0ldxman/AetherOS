"""Где используется ключ во всём проекте.

Условия по ключам живут в разных местах: вики (записи и разделы), приложения
и профили машин, ключи файлов. Админка ключей и сводка автора берут общий
ответ отсюда, чтобы «ключ нигде не используется» было правдой.
"""
from dataclasses import dataclass

from django.urls import reverse

from .access import condition_slugs


@dataclass(frozen=True)
class Usage:
    kind: str    # "запись", "раздел", "приложение", "профиль", "объект", "письмо"
    label: str
    url: str


def _json_conditions():
    """(объект, вид, условие) для всех JSON-условий вне вики."""
    from mail.models import Message
    from machines.models import MachineApp, MachineProfile

    for app in MachineApp.objects.select_related("machine").exclude(key_condition=None):
        yield app, "приложение", app.key_condition
    for profile in MachineProfile.objects.select_related("machine").exclude(key_condition=None):
        yield profile, "профиль", profile.key_condition
    for message in Message.objects.exclude(key_condition=None):
        yield message, "письмо", message.key_condition


_ADMIN = {
    "приложение": "admin:machines_machineapp_change",
    "профиль": "admin:machines_machineprofile_change",
    "письмо": "admin:mail_message_change",
}


def key_usage(slug):
    """Список Usage для ключа: вики, машины, файлы."""
    from filesystem.models import Item, ItemKey, ItemSignature, Placement, Volume
    from wiki.key_usage import key_usage as wiki_usage

    found = []
    found += [
        Usage("запись", item.name, reverse("admin:filesystem_item_change", args=[item.pk])) for item in wiki_usage(slug)
    ]
    for obj, kind, condition in _json_conditions():
        if slug in condition_slugs(condition):
            found.append(Usage(kind, str(obj), reverse(_ADMIN[kind], args=[obj.pk])))
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
    for _, _, condition in _json_conditions():
        slugs.update(condition_slugs(condition))
    slugs.update(ItemKey.objects.values_list("key__slug", flat=True))
    slugs.update(ItemSignature.objects.values_list("key__slug", flat=True))
    for model in (Item, Placement, Volume):
        for access in model.objects.exclude(access={}).values_list("access", flat=True):
            slugs.update(condition_slugs(access))
    return slugs
