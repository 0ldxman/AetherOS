"""Кто какие письма видит и что прочитал.

Ящик это адрес профиля (MachineProfile.mail). Игрок, вошедший под профилем, видит ящик с этим
адресом, безымянный игрок (witness) видит witness@aether-null. Папки:

    inbox   письма, у которых среди получателей подходит мой адрес (маски: *@aether-*);
    sent    письма, отправленные с моего адреса;
    drafts  мои неотправленные;
    trash   письма, положенные в корзину моего профиля (только вошедшему под профилем).

Видимость письма: папка по адресу и ещё два условия: доставка (письмо с идентификатором видно
только тому, кому его доставили, и не раньше времени доставки) и условие по ключам. Скрытое
письмо для игрока не существует (404, а не «нет доступа»).
"""
import copy
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from machines.current import active_session, current_machine
from machines.world import ago
from secure.access import satisfied
from users.aether_auth import GUEST_LOGIN
from wiki.access import request_keys

from .addresses import matches_any, same
from .models import Delivered, Message, MessageRead, Trashed

FOLDERS = ("inbox", "drafts", "sent", "trash")


@dataclass(frozen=True)
class Viewer:
    address: str
    keys: frozenset
    profile: object = None       # профиль, под которым игрок вошёл (у witness его нет)
    user: object = None          # вошедший игрок
    session_key: str = ""        # безымянный игрок (witness): отметки по сессии


def session_key_of(session):
    """Ключ сессии (создаётся, если сессия ещё не сохранена). Для обычного словаря (тесты) пусто."""
    if not hasattr(session, "session_key"):
        return ""
    if session.session_key is None:
        session.save()
    return session.session_key or ""


def guest_address(machine):
    return f"{GUEST_LOGIN}@{machine.label}"


def viewer_for(request):
    """Читатель этого запроса или None, если игрок ещё нигде не подключён."""
    machine = current_machine(request)
    if machine is None:
        return None

    if request.user.is_authenticated:
        profile = active_session(request).profile
        return Viewer(address=profile.mail, keys=request_keys(request), profile=profile, user=request.user)

    return Viewer(
        address=guest_address(machine),
        keys=request_keys(request),
        session_key=session_key_of(request.session),
    )


def folder_of(message, viewer, trashed=frozenset()):
    """В какой папке этого читателя лежит письмо или None, если оно не его."""
    mine = same(message.sender, viewer.address)

    if message.is_draft:
        if not mine:
            return None
    elif not (mine or matches_any(message.recipients, viewer.address)):
        return None

    if message.pk in trashed:
        return "trash"

    if message.is_draft:
        return "drafts"

    if matches_any(message.recipients, viewer.address):
        return "inbox"

    return "sent"


def folders_of(message, viewer, trashed=frozenset()):
    """Все папки читателя, где лежит письмо: себе или своему ящику по маске письмо и во входящих, и в отправленных."""
    where = folder_of(message, viewer, trashed)

    if where == "inbox" and not message.is_draft and same(message.sender, viewer.address):
        return ["inbox", "sent"]

    return [] if where is None else [where]


def _delivered_ids(viewer, now):
    if viewer.user is None:
        return set()
    return set(
        Delivered.objects
        .filter(user=viewer.user, available_at__lte=now)
        .values_list("message_id", flat=True)
    )


def _trashed_ids(viewer):
    if viewer.profile is None:
        return frozenset()
    return frozenset(Trashed.objects.filter(profile=viewer.profile).values_list("message_id", flat=True))


def visible_messages(viewer, folder=None, now=None):
    """Письма читателя (новые первыми). folder: одна папка или все, если None."""
    now = now or timezone.now()
    delivered = _delivered_ids(viewer, now)
    trashed = _trashed_ids(viewer)

    candidates = (
        Message.objects
        .filter(Q(slug__isnull=True) | Q(slug="") | Q(pk__in=delivered))
        .prefetch_related("attachments")
    )
    found = []

    for message in candidates:
        if message.key_condition is not None and not satisfied(message.key_condition, viewer.keys):
            continue

        for where in folders_of(message, viewer, trashed):
            if folder is not None and where != folder:
                continue

            # копия объекта, чтобы у письма в каждой папке была своя отметка папки
            entry = copy.copy(message)
            entry.folder = where
            found.append(entry)

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
        "sender": latest.sender if latest else "",
        "ago": ago(latest.sent_at) if latest else "",
    }
