"""Кто какие письма видит и что прочитал.

Ящик это логин на машине: игрок, вошедший под will_smith на apollo-staff, видит ящик
will_smith@apollo.mail. В ящике три папки:

    inbox   письма этому логину (или всем);
    sent    письма, которые отправил этот логин;
    drafts  неотправленное этого логина.

Видимость письма: машина (или все), папка по логину и ещё два условия: доставка (письмо по
триггеру видно только тому, кому его доставили, и не раньше времени доставки) и условие по
ключам. Скрытое письмо для игрока не существует (404, а не «нет доступа»).
"""
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from machines.current import active_session, current_machine
from machines.world import ago
from secure.access import satisfied
from users.aether_auth import GUEST_LOGIN
from wiki.access import request_keys

from .models import Delivered, Message, MessageRead

FOLDERS = ("inbox", "drafts", "sent")


@dataclass(frozen=True)
class Viewer:
    login: str
    machine: object
    keys: frozenset
    user: object = None          # вошедший игрок
    session_key: str = ""        # безымянный игрок (witness): отметки по сессии

    @property
    def address(self):
        return f"{self.login}@{self.machine.mail_host}"


def session_key_of(session):
    """Ключ сессии (создаётся, если сессия ещё не сохранена). Для обычного словаря (тесты) пусто."""
    if not hasattr(session, "session_key"):
        return ""
    if session.session_key is None:
        session.save()
    return session.session_key or ""


def viewer_for(request):
    """Читатель этого запроса или None, если игрок ещё нигде не подключён."""
    machine = current_machine(request)
    if machine is None:
        return None

    if request.user.is_authenticated:
        return Viewer(
            login=active_session(request).profile.login,
            machine=machine,
            keys=request_keys(request),
            user=request.user,
        )

    return Viewer(
        login=GUEST_LOGIN,
        machine=machine,
        keys=request_keys(request),
        session_key=session_key_of(request.session),
    )


def folder_of(message, viewer):
    """В какой папке этого читателя лежит письмо или None, если оно не его."""
    login = viewer.login.lower()

    if message.is_draft:
        return "drafts" if message.sender_login.lower() == login else None

    if message.to_login == "" or message.to_login.lower() == login:
        return "inbox"

    if message.sender_login and message.sender_login.lower() == login:
        return "sent"

    return None


def _delivered_ids(viewer, now):
    if viewer.user is None:
        return set()
    return set(
        Delivered.objects
        .filter(user=viewer.user, available_at__lte=now)
        .values_list("message_id", flat=True)
    )


def visible_messages(viewer, folder=None, now=None):
    """Письма читателя (новые первыми). folder: одна папка или все, если None."""
    now = now or timezone.now()
    candidates = (
        Message.objects
        .filter(Q(machine=viewer.machine) | Q(machine__isnull=True))
        .prefetch_related("attachments")
    )
    delivered = _delivered_ids(viewer, now)
    found = []

    for message in candidates:
        if message.delivery == Message.Delivery.TRIGGER and message.pk not in delivered:
            continue
        if message.key_condition is not None and not satisfied(message.key_condition, viewer.keys):
            continue

        where = folder_of(message, viewer)
        if where is None or (folder is not None and where != folder):
            continue

        message.folder = where
        found.append(message)

    return found


def _reads(viewer):
    if viewer.user is not None:
        return MessageRead.objects.filter(user=viewer.user)
    if viewer.session_key:
        return MessageRead.objects.filter(session_key=viewer.session_key)
    return MessageRead.objects.none()


def read_ids(viewer):
    return set(_reads(viewer).values_list("message_id", flat=True))


def mark_read(viewer, message):
    if viewer.user is not None:
        MessageRead.objects.get_or_create(message=message, user=viewer.user)
    elif viewer.session_key:
        MessageRead.objects.get_or_create(message=message, session_key=viewer.session_key)


def mark_unread(viewer, message):
    _reads(viewer).filter(message=message).delete()


def summary(viewer):
    """Для приветствия узла: сколько непрочитанных во входящих и от кого последнее."""
    inbox = visible_messages(viewer, "inbox")
    done = read_ids(viewer)
    unread = [m for m in inbox if m.id not in done]
    latest = unread[0] if unread else None
    return {
        "unread": len(unread),
        "sender": latest.sender_name if latest else "",
        "ago": ago(latest.sent_at) if latest else "",
    }
