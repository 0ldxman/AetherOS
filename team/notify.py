"""Уведомления авторам на Главной: назначили задачу, упомянули в обсуждении, срок задачи подходит или прошёл."""
import datetime as dt

from django.db import IntegrityError, transaction
from django.utils import timezone

from team.models import Notification, Task

DUE_SOON_DAYS = 2
LIMIT = 30


def send(user, kind, text, link, key):
    """Одно уведомление на ключ: повтор с тем же ключом не создаётся."""
    if user is None or not user.is_staff:
        return None
    try:
        with transaction.atomic():
            return Notification.objects.create(user=user, kind=kind, text=text[:300], link=link[:255], key=key[:120])
    except IntegrityError:
        return None


def assigned(actor, task, users):
    for user in users:
        if user.pk != actor.pk:
            send(user, "assigned", f"{actor.get_username()} назначил(а) вам задачу «{task.title}».", f"#/tasks/{task.pk}",
                 f"assigned:{task.pk}:{timezone.now():%Y%m%d%H%M%S%f}")


def mentioned(actor, comment, users):
    where = f"{comment.kind} {comment.label}".strip()
    for user in users:
        if user.pk != actor.pk:
            send(user, "mention", f"{actor.get_username()} упомянул(а) вас в обсуждении: {where}.", comment.link, f"mention:{comment.pk}")


def deadlines(user, today=None):
    """Напомнить о сроках открытых задач автора: подходит (за два дня) или прошёл. Раз на задачу и день."""
    today = today or timezone.localdate()
    soon = today + dt.timedelta(days=DUE_SOON_DAYS)
    for task in Task.objects.filter(assignees=user, due__isnull=False, due__lte=soon).exclude(status=Task.Status.DONE):
        if task.due < today:
            send(user, "overdue", f"Срок задачи «{task.title}» прошёл {task.due:%d.%m}.", f"#/tasks/{task.pk}", f"overdue:{task.pk}:{today}")
        else:
            left = (task.due - today).days
            when = "сегодня" if left == 0 else "завтра" if left == 1 else f"через {left} дня"
            send(user, "due", f"Срок задачи «{task.title}» {when}.", f"#/tasks/{task.pk}", f"due:{task.pk}:{today}")


def inbox(user):
    deadlines(user)
    found = Notification.objects.filter(user=user)
    return list(found[:LIMIT]), found.filter(read_at__isnull=True).count()


def read(user, ids=None):
    found = Notification.objects.filter(user=user, read_at__isnull=True)
    if ids:
        found = found.filter(pk__in=ids)
    return found.update(read_at=timezone.now())
