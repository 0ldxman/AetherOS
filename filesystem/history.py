"""История версий и мягкая блокировка объектов (то, что вики делала для записей).

Версия: record_revision вызывается по post_save объекта и добавляет снимок, если содержимое изменилось с прошлого раза.
Блокировка: страница редактора раз в HEARTBEAT секунд вызывает acquire; объект считается свободным, если сигналов не было
дольше LOCK_TTL.
"""
import difflib
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from filesystem.models import ItemLock, ItemRevision

SNAPSHOT_FIELDS = ("name", "format", "body", "meta")
LABELS = {"name": "Название", "format": "Формат", "body": "Текст", "meta": "Метаинформация"}

LOCK_TTL = timedelta(seconds=90)
HEARTBEAT_SECONDS = 25


# ---- версии ---------------------------------------------------------------------------------------------------------

def snapshot(obj):
    return {name: getattr(obj, name) for name in SNAPSHOT_FIELDS}


def record_revision(item):
    """Снимок текущего состояния объекта; None, если оно совпадает с последним или объект не текстовый."""
    current = snapshot(item)
    last = ItemRevision.objects.filter(item=item).first()
    if last is None and not (item.body or item.meta):
        return None                             # у объекта нет текста: истории вести нечего (ключи, ассеты, пустые файлы)
    if last is not None and snapshot(last) == current:
        return None
    return ItemRevision.objects.create(item=item, saved_by=item.updated_by, **current)


def on_item_saved(sender, instance, **kwargs):
    if kwargs.get("raw"):                       # загрузка фикстур: историю не трогаем
        return
    record_revision(instance)


def diff_rows(old, new, context=3):
    """Построчная разница двух текстов -> [(вид, строка)]: add, del, same или hunk (заголовок блока изменений)."""
    rows = []
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), n=context, lineterm=""):
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            rows.append(("hunk", line))
        elif line.startswith("+"):
            rows.append(("add", line[1:]))
        elif line.startswith("-"):
            rows.append(("del", line[1:]))
        else:
            rows.append(("same", line[1:]))
    return rows


def compare(old, new):
    """Различия между двумя снимками (или объектом): словарь по изменившимся полям."""
    result = {}
    for name in ("name", "format"):
        before, after = getattr(old, name), getattr(new, name)
        if before != after:
            result[name] = (before, after)
    for name in ("body", "meta"):
        before, after = getattr(old, name), getattr(new, name)
        if before != after:
            result[name] = diff_rows(before, after)
    return result


def restore(item, revision, user):
    """Вернуть объекту текст версии (название, формат, тело, врезку). Новая версия появится сама (on_item_saved)."""
    for name in SNAPSHOT_FIELDS:
        setattr(item, name, getattr(revision, name))
    item.updated_by = user
    item.full_clean(exclude=["created_by", "updated_by"])
    item.save()
    return item


# ---- блокировка -----------------------------------------------------------------------------------------------------

def is_active(lock, now):
    return now - lock.refreshed_at < LOCK_TTL


def acquire(item, user):
    """Занять объект или продлить своё занятие. Возвращает чужую блокировку, если занят другим, иначе None."""
    now = timezone.now()
    with transaction.atomic():
        lock = ItemLock.objects.select_for_update().select_related("user").filter(item=item).first()
        if lock is None:
            ItemLock.objects.create(item=item, user=user, refreshed_at=now)
            return None
        if lock.user_id == user.pk:
            lock.refreshed_at = now
            lock.save(update_fields=["refreshed_at"])
            return None
        if not is_active(lock, now):
            lock.user, lock.acquired_at, lock.refreshed_at = user, now, now
            lock.save()
            return None
        return lock


def release(item, user):
    """Снять своё занятие; чужое не трогает."""
    ItemLock.objects.filter(item=item, user=user).delete()


def holder(item, now=None):
    """Блокировка, которая сейчас действует, или None."""
    now = now or timezone.now()
    lock = ItemLock.objects.select_related("user").filter(item=item).first()
    return lock if lock is not None and is_active(lock, now) else None
