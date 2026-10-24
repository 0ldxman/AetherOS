"""Где используется ключ во всём проекте.

Условия по ключам живут в разных местах: вики (записи и разделы), приложения
и профили машин, ключи файлов. Админка ключей и сводка автора берут общий
ответ отсюда, чтобы «ключ нигде не используется» было правдой.
Держатели ключа (у кого он есть) сюда не входят: это отдельная связь.
"""
from dataclasses import dataclass

from django.urls import reverse

from .access import condition_slugs


@dataclass(frozen=True)
class Usage:
    kind: str    # "запись", "раздел", "приложение", "профиль", "файл"
    label: str
    url: str


def _json_conditions():
    """(объект, вид, условие) для всех JSON-условий вне вики."""
    from machines.models import MachineApp, MachineProfile

    for app in MachineApp.objects.select_related("machine").exclude(key_condition=None):
        yield app, "приложение", app.key_condition
    for profile in MachineProfile.objects.select_related("machine").exclude(key_condition=None):
        yield profile, "профиль", profile.key_condition


_ADMIN = {
    "приложение": "admin:machines_machineapp_change",
    "профиль": "admin:machines_machineprofile_change",
}


def key_usage(slug):
    """Список Usage для ключа: вики, машины, файлы."""
    from filesystem.models import FileKey
    from wiki.key_usage import key_usage as wiki_usage

    found = []
    documents, namespaces = wiki_usage(slug)
    found += [
        Usage("запись", d.path(), reverse("admin:wiki_document_change", args=[d.pk])) for d in documents
    ]
    found += [
        Usage("раздел", n.path(), reverse("admin:wiki_namespace_change", args=[n.pk])) for n in namespaces
    ]
    for obj, kind, condition in _json_conditions():
        if slug in condition_slugs(condition):
            found.append(Usage(kind, str(obj), reverse(_ADMIN[kind], args=[obj.pk])))
    for link in FileKey.objects.filter(key__slug=slug).select_related("file__machine"):
        found.append(
            Usage("файл", str(link.file), reverse("admin:filesystem_machinefile_change", args=[link.file_id]))
        )
    return found


def used_slugs():
    """Множество slug'ов ключей, встречающихся вне вики (машины и файлы)."""
    from filesystem.models import FileKey

    slugs = set()
    for _, _, condition in _json_conditions():
        slugs.update(condition_slugs(condition))
    slugs.update(FileKey.objects.values_list("key__slug", flat=True))
    return slugs
