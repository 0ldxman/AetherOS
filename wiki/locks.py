"""Мягкая блокировка записи на время правки в админке.

Страница редактора раз в HEARTBEAT секунд вызывает acquire; запись
считается свободной, если сигналов не было дольше LOCK_TTL.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import DocumentLock

LOCK_TTL = timedelta(seconds=90)
HEARTBEAT_SECONDS = 25  # как часто страница подтверждает, что правка идёт


def is_active(lock, now):
    return now - lock.refreshed_at < LOCK_TTL


def acquire(doc, user):
    """Занять запись или продлить своё занятие.

    Возвращает чужую блокировку, если запись занята другим, иначе None.
    """
    now = timezone.now()
    with transaction.atomic():
        lock = (
            DocumentLock.objects.select_for_update()
            .select_related("user")
            .filter(document=doc)
            .first()
        )
        if lock is None:
            DocumentLock.objects.create(document=doc, user=user, refreshed_at=now)
            return None
        if lock.user_id == user.pk:
            lock.refreshed_at = now
            lock.save(update_fields=["refreshed_at"])
            return None
        if not is_active(lock, now):
            lock.user = user
            lock.acquired_at = now
            lock.refreshed_at = now
            lock.save()
            return None
        return lock


def release(doc, user):
    """Снять своё занятие; чужое не трогает."""
    DocumentLock.objects.filter(document=doc, user=user).delete()


def holder(doc, now=None):
    """Блокировка, которая сейчас действует, или None."""
    now = now or timezone.now()
    lock = DocumentLock.objects.select_related("user").filter(document=doc).first()
    return lock if lock is not None and is_active(lock, now) else None
