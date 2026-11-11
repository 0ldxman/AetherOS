"""Техподдержка: очередь обращений игроков, ответы, заметки команды, вложения. Логика в support.desk."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from support import desk
from support.models import Ticket

router = Router(tags=["support"])


class SpRow(Schema):
    id: int
    subject: str
    category: str
    status: str
    player: str
    player_id: int
    assignee: str
    assignee_id: int | None
    updated_at: dt.datetime
    waiting_on_team: bool        # последнее слово за игроком


class SpFile(Schema):
    id: int
    name: str
    size: int
    image: bool


class SpMessage(Schema):
    id: int
    staff: bool
    internal: bool
    author: str
    text: str
    created_at: dt.datetime
    files: list[SpFile]


class SpTicket(SpRow):
    context: dict
    created_at: dt.datetime
    messages: list[SpMessage]


class SpMeta(Schema):
    statuses: list[dict[str, str]]
    categories: list[dict[str, str]]
    authors: list[dict[str, str | int]]


class SpChange(Schema):
    status: str | None = None
    assignee: int | None = None
    unassign: bool = False


def _last_player(ticket):
    last = ticket.messages.filter(internal=False).order_by("-created_at").first()
    return last is not None and not last.staff


def _row(ticket):
    return dict(id=ticket.pk, subject=ticket.subject, category=ticket.category, status=ticket.status, player=ticket.user.get_username(),
                player_id=ticket.user_id, assignee=ticket.assignee.get_username() if ticket.assignee_id else "", assignee_id=ticket.assignee_id,
                updated_at=ticket.updated_at, waiting_on_team=ticket.status != Ticket.Status.CLOSED and _last_player(ticket))


def _ticket(ticket):
    messages = [SpMessage(id=m.pk, staff=m.staff, internal=m.internal, author=m.author.get_username() if m.author_id else "?", text=m.text,
                          created_at=m.created_at, files=[SpFile(id=f.pk, name=f.name, size=f.size, image=f.is_image) for f in m.files.all()])
                for m in desk.visible(ticket, staff=True)]
    return SpTicket(**_row(ticket), context=ticket.context or {}, created_at=ticket.created_at, messages=messages)


@router.get("/meta", response=SpMeta)
def meta(request):
    from team import rights

    authors = [u for u in get_user_model().objects.filter(is_staff=True, is_active=True).order_by("username") if rights.level_of(u, "support") != rights.NONE]
    return SpMeta(statuses=[{"value": v, "label": l} for v, l in Ticket.Status.choices],
                  categories=[{"value": v, "label": l} for v, l in Ticket.Category.choices],
                  authors=[{"id": u.pk, "username": u.get_username()} for u in authors])


@router.get("", response=list[SpRow])
def index(request, status: str = "", mine: bool = False):
    tickets = Ticket.objects.select_related("user", "assignee")
    if status == "active":
        tickets = tickets.exclude(status=Ticket.Status.CLOSED)
    elif status:
        tickets = tickets.filter(status=status)
    if mine:
        tickets = tickets.filter(assignee=request.user)
    return [SpRow(**_row(t)) for t in tickets[:300]]


@router.get("/{ticket_id}", response=SpTicket)
def detail(request, ticket_id: int):
    return _ticket(get_object_or_404(Ticket, pk=ticket_id))


@router.post("/{ticket_id}/reply", response=SpTicket)
def reply(request, ticket_id: int, text: Form[str] = "", internal: Form[bool] = False, files: File[list[UploadedFile]] = None):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    desk.staff_reply(ticket, request.user, text, files or [], internal=internal)
    return _ticket(ticket)


@router.put("/{ticket_id}", response=SpTicket)
def change(request, ticket_id: int, body: SpChange):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if body.status:
        desk.set_status(ticket, body.status)
    if body.unassign:
        desk.assign(ticket, None)
    elif body.assignee:
        desk.assign(ticket, get_object_or_404(get_user_model(), pk=body.assignee, is_staff=True))
    return _ticket(ticket)


@router.get("/files/{file_id}", response={200: None})
def file(request, file_id: int):
    found = desk.file_of(file_id, staff=True)
    if found is None:
        return HttpResponse(status=404)
    response = HttpResponse(bytes(found.data), content_type=found.content_type or "application/octet-stream")
    response["Content-Disposition"] = f'{"inline" if desk.inline(found) else "attachment"}; filename="{found.name.replace(chr(34), "")}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
