"""Обсуждения сущностей Студии: ветки, ответы, упоминания, «решено». Писать может любой автор. Логика в team.comments."""
import datetime as dt

from django.contrib.auth import get_user_model
from ninja import Router, Schema
from ninja.errors import HttpError

from team import comments as logic

router = Router(tags=["comments"])


class CmMessage(Schema):
    id: int
    username: str
    text: str
    mentions: list[str]
    created_at: dt.datetime
    edited_at: dt.datetime | None
    own: bool


class CmThread(Schema):
    id: int
    resolved_at: dt.datetime | None
    resolved_by: str
    messages: list[CmMessage]


class CmIn(Schema):
    target: str = ""
    text: str
    parent: int | None = None


class CmEdit(Schema):
    text: str


class CmResolve(Schema):
    resolved: bool


class CmInboxRow(Schema):
    thread: int
    target: str
    kind: str
    label: str
    link: str
    count: int
    last_by: str
    last_text: str
    last_at: dt.datetime
    mentioned: bool
    waiting: bool


class CmInbox(Schema):
    rows: list[CmInboxRow]
    open_total: int


class CmAuthor(Schema):
    username: str


def _message(c, user):
    return CmMessage(id=c.pk, username=c.username, text=c.text, mentions=[u.get_username() for u in c.mentions.all()],
                     created_at=c.created_at, edited_at=c.edited_at, own=c.author_id == user.pk)


def _thread(root, user):
    return CmThread(id=root.pk, resolved_at=root.resolved_at, resolved_by=root.resolved_by,
                    messages=[_message(m, user) for m in [root, *root.replies.all()]])


def _call(fn):
    try:
        return fn()
    except logic.CommentError as exc:
        raise HttpError(400, str(exc))


@router.get("", response=list[CmThread])
def comment_threads(request, target: str):
    return [_thread(root, request.user) for root in _call(lambda: logic.threads(target))]


@router.get("/counts", response=dict[str, int])
def comment_counts(request, targets: str = ""):
    """Открытые ветки по сущностям: targets через запятую."""
    return logic.counts([t.strip().strip("/") for t in targets.split(",") if t.strip()])


@router.get("/inbox", response=CmInbox)
def comment_inbox(request):
    rows = [CmInboxRow(thread=r["root"].pk, target=r["root"].target, kind=r["root"].kind, label=r["root"].label, link=r["root"].link,
                       count=r["count"], last_by=r["last"].username, last_text=r["last"].text[:200], last_at=r["last"].created_at,
                       mentioned=r["mentioned"], waiting=r["waiting"]) for r in logic.inbox(request.user)]
    return CmInbox(rows=rows, open_total=logic.open_total())


@router.get("/authors", response=list[CmAuthor])
def comment_authors(request):
    """Кого можно упомянуть: авторы команды."""
    return [CmAuthor(username=u.get_username()) for u in get_user_model().objects.filter(is_staff=True).order_by("username")]


@router.post("", response=CmThread)
def comment_post(request, body: CmIn):
    comment = _call(lambda: logic.post(request.user, body.target, body.text, body.parent))
    root = comment.parent or comment
    root.refresh_from_db()
    return _thread(root, request.user)


@router.put("/{int:comment_id}", response=CmMessage)
def comment_edit(request, comment_id: int, body: CmEdit):
    return _message(_call(lambda: logic.edit(request.user, comment_id, body.text)), request.user)


@router.delete("/{int:comment_id}", response={204: None})
def comment_delete(request, comment_id: int):
    _call(lambda: logic.delete(request.user, comment_id))
    return 204, None


@router.post("/{int:comment_id}/resolve", response=CmThread)
def comment_resolve(request, comment_id: int, body: CmResolve):
    root = _call(lambda: logic.resolve(request.user, comment_id, body.resolved))
    return _thread(root, request.user)
