"""Задачи команды: статус, исполнители, приоритет 1–10, срок, метки, ссылки на сущности мира.

Сущность в ссылке называется путём API, как в ленте и обсуждениях (machines/3); вид, подпись и ссылка в Студии берутся
оттуда же (team.changes.describe). У задачи своё обсуждение: комментарии на цели tasks/<id>.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from team import changes, notify
from team.models import Comment, Task

STATUSES = [value for value, _ in Task.Status.choices]


class TaskError(Exception):
    pass


def _link(target):
    target = (target or "").strip().strip("/")
    if not target:
        raise TaskError("Пустая ссылка на сущность.")
    kind, label, link, _, _ = changes.describe(target)
    return {"target": target, "kind": kind, "label": label, "link": link}


def _clean(data):
    title = (data.get("title") or "").strip()
    if not title:
        raise TaskError("Назовите задачу.")
    status = data.get("status") or Task.Status.OPEN
    if status not in STATUSES:
        raise TaskError("Неизвестный статус.")
    try:
        priority = int(data.get("priority") or 5)
    except (TypeError, ValueError):
        raise TaskError("Приоритет это число от 1 до 10.")
    if not 1 <= priority <= 10:
        raise TaskError("Приоритет это число от 1 до 10.")
    labels = list(dict.fromkeys(str(label).strip().lower() for label in data.get("labels") or [] if str(label).strip()))
    return {"title": title[:200], "body": data.get("body") or "", "status": status, "priority": priority, "due": data.get("due"), "labels": labels}


def _assignees(ids):
    users = list(get_user_model().objects.filter(pk__in=ids or [], is_staff=True))
    if len(users) != len(set(ids or [])):
        raise TaskError("Исполнителем может быть только автор команды.")
    return users


@transaction.atomic
def save(actor, task, data):
    """Создать или изменить задачу; новым исполнителям уходит уведомление."""
    fields = _clean(data)
    links = [_link(entry.get("target") if isinstance(entry, dict) else entry) for entry in data.get("links") or []]
    users = _assignees(data.get("assignees"))
    fresh = task.pk is None
    for key, value in fields.items():
        setattr(task, key, value)
    task.links = list({entry["target"]: entry for entry in links}.values())
    if fresh:
        task.created_by = actor
    task.save()
    before = set() if fresh else set(task.assignees.values_list("pk", flat=True))
    task.assignees.set(users)
    notify.assigned(actor, task, [user for user in users if user.pk not in before])
    return task


def move(task, status):
    if status not in STATUSES:
        raise TaskError("Неизвестный статус.")
    task.status = status
    task.save(update_fields=["status", "updated_at"])
    return task


def delete(actor, task):
    if not actor.is_superuser and task.created_by_id != actor.pk:
        raise TaskError("Задачу удаляет тот, кто её завёл, или суперадмин.")
    Comment.objects.filter(target=f"tasks/{task.pk}").delete()
    task.delete()


def from_thread(actor, thread_id):
    """Задача из ветки обсуждения: первое сообщение в описание, сущность ветки в ссылки, в ветке ответ со ссылкой на задачу."""
    from team import comments

    root = Comment.objects.filter(pk=thread_id, parent__isnull=True).first()
    if root is None:
        raise TaskError("Такой ветки нет.")
    first_line = root.text.strip().splitlines()[0] if root.text.strip() else "Задача из обсуждения"
    task = save(actor, Task(), {"title": first_line[:120], "body": root.text, "links": [root.target] if not root.target.startswith("tasks/") else []})
    comments.post(actor, root.target, f"Сделана задача: «{task.title}» (#/tasks/{task.pk})", parent_id=root.pk)
    return task


def search(user=None, status="", assignee=None, label="", target="", overdue=False, query=""):
    found = Task.objects.prefetch_related("assignees").select_related("created_by")
    if status:
        found = found.filter(status__in=status.split(","))
    if assignee:
        found = found.filter(assignees__pk=assignee)
    if target:
        target = target.strip("/")
        found = [task for task in found if any(entry.get("target") == target for entry in task.links)]
    if label:
        found = [task for task in found if label.lower() in task.labels]
    if overdue:
        today = timezone.localdate()
        found = [task for task in found if task.due and task.due < today and task.status != Task.Status.DONE]
    if query:
        needle = query.lower()
        found = [task for task in found if needle in task.title.lower() or needle in task.body.lower()]
    return list(found)


def mine_open(user):
    return list(Task.objects.filter(assignees=user).exclude(status=Task.Status.DONE).prefetch_related("assignees"))
