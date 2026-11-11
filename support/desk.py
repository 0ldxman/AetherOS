"""Обращения в поддержку: игрок пишет, команда отвечает. Здесь вся логика: приложение игрока (support/views.py)
и Студия (studio/api/support.py) только обёртки.

Статусы: new (никто не ответил) → open (взято в работу) → waiting (команда ответила, ждём игрока) → closed.
Ответ игрока возвращает обращение в open (закрытое тоже открывается заново). Заметка команды (internal) статус не меняет.
"""
import mimetypes
import posixpath

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from support.models import IMAGE_TYPES, Ticket, TicketFile, TicketMessage

MAX_FILES = 5
MAX_SIZE = 5 * 1024 * 1024
MAX_TEXT = 5000


def context_of(request):
    """Где был игрок, когда писал: машина, учётка, браузер. Чтобы не объяснять это словами."""
    from machines.current import active_session, current_machine

    found = {"user_agent": request.META.get("HTTP_USER_AGENT", "")[:300]}
    machine = current_machine(request)
    if machine is not None:
        found.update({"machine": machine.label, "machine_id": machine.pk})
    session = active_session(request) if request.user.is_authenticated else None
    if session is not None and getattr(session, "profile", None) is not None:
        found.update({"login": session.profile.login, "profile_id": session.profile.pk})
    return found


def _files(message, uploads):
    uploads = list(uploads or [])
    if len(uploads) > MAX_FILES:
        raise ValidationError({"files": [f"Не больше {MAX_FILES} файлов."]})
    for upload in uploads:
        if upload.size > MAX_SIZE:
            raise ValidationError({"files": [f"{upload.name}: больше {MAX_SIZE // (1024 * 1024)} МБ."]})
    for upload in uploads:
        name = posixpath.basename((upload.name or "file").replace("\\", "/"))[:200] or "file"
        kind = (getattr(upload, "content_type", "") or mimetypes.guess_type(name)[0] or "application/octet-stream")[:100]
        TicketFile.objects.create(message=message, name=name, content_type=kind, size=upload.size, data=upload.read())


def _message(ticket, author, text, uploads, staff=False, internal=False):
    text = (text or "").strip()[:MAX_TEXT]
    if not text and not uploads:
        raise ValidationError({"text": ["Пустое сообщение."]})
    message = TicketMessage.objects.create(ticket=ticket, author=author, staff=staff, internal=internal, text=text)
    _files(message, uploads)
    return message


def _notify_team(ticket, text, key):
    from team import notify, rights

    for user in get_user_model().objects.filter(is_staff=True, is_active=True):
        if rights.level_of(user, "support") == rights.NONE:
            continue
        if ticket.assignee_id and user.pk != ticket.assignee_id:
            continue                                         # назначенное обращение: только исполнителю
        notify.send(user, "support", text, f"#/support/{ticket.pk}", key)


@transaction.atomic
def open_ticket(user, *, subject, category, text, uploads=(), context=None):
    subject = (subject or "").strip()[:200]
    if not subject:
        raise ValidationError({"subject": ["Нужна тема."]})
    if category not in Ticket.Category.values:
        category = Ticket.Category.OTHER
    ticket = Ticket.objects.create(user=user, subject=subject, category=category, context=context or {}, player_seen_at=timezone.now())
    _message(ticket, user, text, uploads)
    _notify_team(ticket, f"Новое обращение от {user.get_username()}: «{ticket.subject}».", f"support:{ticket.pk}:new")
    return ticket


@transaction.atomic
def player_reply(ticket, user, text, uploads=()):
    message = _message(ticket, user, text, uploads)
    if ticket.status != Ticket.Status.NEW:
        ticket.status = Ticket.Status.OPEN
    ticket.player_seen_at = timezone.now()
    ticket.save(update_fields=["status", "player_seen_at", "updated_at"])
    _notify_team(ticket, f"{user.get_username()}: новое сообщение в обращении «{ticket.subject}».", f"support:{ticket.pk}:m{message.pk}")
    return message


@transaction.atomic
def staff_reply(ticket, author, text, uploads=(), internal=False):
    message = _message(ticket, author, text, uploads, staff=True, internal=internal)
    fields = ["updated_at"]
    if not internal:
        ticket.status = Ticket.Status.WAITING
        fields.append("status")
        if ticket.assignee_id is None:
            ticket.assignee = author
            fields.append("assignee")
    ticket.save(update_fields=fields)
    return message


def set_status(ticket, status):
    if status not in Ticket.Status.values:
        raise ValidationError({"status": ["Нет такого статуса."]})
    ticket.status = status
    ticket.save(update_fields=["status", "updated_at"])
    return ticket


def assign(ticket, user):
    ticket.assignee = user
    if user is not None and ticket.status == Ticket.Status.NEW:
        ticket.status = Ticket.Status.OPEN
    ticket.save(update_fields=["assignee", "status", "updated_at"])
    return ticket


def visible(ticket, staff=False):
    """Сообщения обращения: игроку без заметок команды."""
    found = ticket.messages.select_related("author").prefetch_related("files")
    return list(found if staff else found.filter(internal=False))


def unread_for(ticket):
    """Есть ли у игрока непрочитанный ответ команды."""
    last = ticket.messages.filter(staff=True, internal=False).order_by("-created_at").values_list("created_at", flat=True).first()
    return last is not None and (ticket.player_seen_at is None or last > ticket.player_seen_at)


def seen(ticket):
    ticket.player_seen_at = timezone.now()
    Ticket.objects.filter(pk=ticket.pk).update(player_seen_at=ticket.player_seen_at)


def pulse(user):
    rows = [ticket for ticket in Ticket.objects.filter(user=user).exclude(status=Ticket.Status.CLOSED) if unread_for(ticket)]
    return {"unread": len(rows), "items": [{"id": ticket.pk, "title": ticket.subject} for ticket in rows[:20]]}


def file_of(file_id, *, user=None, staff=False):
    """Вложение по номеру: игроку только из своих обращений и не из заметок команды."""
    found = TicketFile.objects.select_related("message__ticket").filter(pk=file_id).first()
    if found is None:
        return None
    if staff:
        return found
    if user is None or found.message.ticket.user_id != user.pk or found.message.internal:
        return None
    return found


def inline(file):
    return file.content_type in IMAGE_TYPES
