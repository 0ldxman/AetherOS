"""Кто какие письма видит и что прочитал.

Видимость: машина (или все), адресат (логин на машине или все) и условие по ключам.
Письмо, которое игроку не видно, для него не существует (404, а не «нет доступа»).
"""
from dataclasses import dataclass

from django.db.models import Q

from machines.current import active_session, current_machine
from machines.world import ago
from secure.access import satisfied
from users.aether_auth import GUEST_LOGIN
from wiki.access import request_keys

from .models import Message, MessageRead


@dataclass(frozen=True)
class Viewer:
    login: str
    machine: object
    keys: frozenset
    user: object = None          # вошедший игрок
    session_key: str = ""        # безымянный игрок (witness): отметки по сессии


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


def visible_messages(viewer):
    """Письма читателя, новые первыми."""
    candidates = (
        Message.objects
        .filter(Q(machine=viewer.machine) | Q(machine__isnull=True))
        .filter(Q(to_login="") | Q(to_login__iexact=viewer.login))
        .prefetch_related("attachments")
    )
    return [m for m in candidates if m.key_condition is None or satisfied(m.key_condition, viewer.keys)]


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
    """Для приветствия узла: сколько непрочитанных и от кого последнее: {"unread", "sender", "ago"}."""
    messages = visible_messages(viewer)
    done = read_ids(viewer)
    unread = [m for m in messages if m.id not in done]
    latest = unread[0] if unread else None
    return {
        "unread": len(unread),
        "sender": latest.sender_name if latest else "",
        "ago": ago(latest.sent_at) if latest else "",
    }
