"""Задачи команды и уведомления авторов. Логика в team.tasks и team.notify; задачи правит любой автор."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from team import notify, tasks as logic
from team.models import Task

router = Router(tags=["tasks"])
notifications = Router(tags=["notifications"])


class TkLink(Schema):
    target: str
    kind: str
    label: str
    link: str


class TkOut(Schema):
    id: int
    title: str
    body: str
    status: str
    status_label: str
    priority: int
    due: dt.date | None
    overdue: bool
    labels: list[str]
    links: list[TkLink]
    assignees: list[int]
    assignee_names: list[str]
    created_by: str
    created_at: dt.datetime
    updated_at: dt.datetime
    deletable: bool


class TkIn(Schema):
    title: str
    body: str = ""
    status: str = "open"
    priority: int = 5
    due: dt.date | None = None
    labels: list[str] = []
    links: list[str] = []          # пути API сущностей
    assignees: list[int] = []


class TkMove(Schema):
    status: str


class TkThread(Schema):
    thread: int


class TkMeta(Schema):
    statuses: list[dict[str, str]]
    authors: list[dict[str, str | int]]
    labels: list[str]


class NtRow(Schema):
    id: int
    kind: str
    text: str
    link: str
    created_at: dt.datetime
    read: bool


class NtInbox(Schema):
    rows: list[NtRow]
    unread: int


class NtRead(Schema):
    ids: list[int] = []


def _out(task, user):
    from django.utils import timezone

    today = timezone.localdate()
    return TkOut(
        id=task.pk, title=task.title, body=task.body, status=task.status, status_label=task.get_status_display(), priority=task.priority,
        due=task.due, overdue=bool(task.due and task.due < today and task.status != Task.Status.DONE), labels=task.labels,
        links=[TkLink(**entry) for entry in task.links], assignees=[u.pk for u in task.assignees.all()],
        assignee_names=[u.get_username() for u in task.assignees.all()], created_by=task.created_by.get_username() if task.created_by else "",
        created_at=task.created_at, updated_at=task.updated_at, deletable=user.is_superuser or task.created_by_id == user.pk,
    )


def _call(fn):
    try:
        return fn()
    except logic.TaskError as exc:
        raise HttpError(400, str(exc))


@router.get("", response=list[TkOut])
def task_list(request, status: str = "", assignee: int | None = None, label: str = "", target: str = "", overdue: bool = False, q: str = "", mine: bool = False):
    found = logic.search(status=status, assignee=request.user.pk if mine else assignee, label=label, target=target, overdue=overdue, query=q)
    return [_out(task, request.user) for task in found]


@router.get("/meta", response=TkMeta)
def task_meta(request):
    """Статусы, авторы (кого назначить) и уже встречавшиеся метки."""
    labels = sorted({label for task in Task.objects.only("labels") for label in task.labels})
    authors = [{"id": u.pk, "username": u.get_username()} for u in get_user_model().objects.filter(is_staff=True).order_by("username")]
    return TkMeta(statuses=[{"value": value, "label": label} for value, label in Task.Status.choices], authors=authors, labels=labels)


@router.get("/{int:task_id}", response=TkOut)
def task_get(request, task_id: int):
    return _out(get_object_or_404(Task, pk=task_id), request.user)


@router.post("", response=TkOut)
def task_create(request, body: TkIn):
    return _out(_call(lambda: logic.save(request.user, Task(), body.dict())), request.user)


@router.put("/{int:task_id}", response=TkOut)
def task_update(request, task_id: int, body: TkIn):
    task = get_object_or_404(Task, pk=task_id)
    return _out(_call(lambda: logic.save(request.user, task, body.dict())), request.user)


@router.post("/{int:task_id}/move", response=TkOut)
def task_move(request, task_id: int, body: TkMove):
    task = get_object_or_404(Task, pk=task_id)
    return _out(_call(lambda: logic.move(task, body.status)), request.user)


@router.delete("/{int:task_id}", response={204: None})
def task_delete(request, task_id: int):
    task = get_object_or_404(Task, pk=task_id)
    _call(lambda: logic.delete(request.user, task))
    return 204, None


@router.post("/from-thread", response=TkOut)
def task_from_thread(request, body: TkThread):
    return _out(_call(lambda: logic.from_thread(request.user, body.thread)), request.user)


@notifications.get("", response=NtInbox)
def notification_inbox(request):
    rows, unread = notify.inbox(request.user)
    return NtInbox(rows=[NtRow(id=n.pk, kind=n.kind, text=n.text, link=n.link, created_at=n.created_at, read=n.read_at is not None) for n in rows], unread=unread)


@notifications.post("/read", response=NtInbox)
def notification_read(request, body: NtRead):
    notify.read(request.user, body.ids or None)
    return notification_inbox(request)
