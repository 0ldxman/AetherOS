import re
from datetime import timezone

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from machines.current import active_session
from users.aether_auth import AUTH_REQUIRED, is_player

from .access import mark_read, mark_unread, read_ids, viewer_for, visible_messages
from .attachments import SaveError, payload, save_to_machine
from .models import Attachment

PREVIEW_LENGTH = 90


def _when(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _sender(message):
    if message.sender_address:
        return f"{message.sender_name} <{message.sender_address}>"
    return message.sender_name


def _plain(text):
    """Текст без разметки письма (# - > ** * `): для превью в карточке."""
    text = re.sub(r"^\s*(#{1,3}\s+|[-*]\s+|>\s?)", "", text, flags=re.MULTILINE)
    return " ".join(re.sub(r"(\*\*|\*|`)", "", text).split())


def _row(message, unread):
    body = _plain(message.body)
    return {
        "id": message.pk,
        "sender": message.sender_name,
        "subject": message.subject or "(no subject)",
        "when": _when(message.sent_at),
        "unread": unread,
        "folder": getattr(message, "folder", "inbox"),
        "note": message.status_note,
        "label": message.label,
        "tone": message.label_tone,
        "preview": body[:PREVIEW_LENGTH] + ("…" if len(body) > PREVIEW_LENGTH else ""),
        "attachments": len(message.attachments.all()),
    }


def _viewer_or_404(request):
    viewer = viewer_for(request)
    if viewer is None:
        raise Http404
    return viewer


@ensure_csrf_cookie
def inbox(request):
    viewer = _viewer_or_404(request)
    return render(request, "mail/inbox.html", {"address": viewer.address})


@require_GET
def message_list(request):
    viewer = _viewer_or_404(request)
    done = read_ids(viewer)
    messages = visible_messages(viewer)
    # непрочитанность важна только во входящих: черновики и отправленное «прочитаны» всегда
    return JsonResponse({
        "address": viewer.address,
        "messages": [_row(m, m.folder == "inbox" and m.pk not in done) for m in messages],
    })


def _find(viewer, pk):
    for message in visible_messages(viewer):
        if message.pk == pk:
            return message
    raise Http404     # чужое и скрытое письмо выглядит как несуществующее


@require_GET
def message_detail(request, pk):
    """Письмо целиком. Открытие отмечает его прочитанным."""
    viewer = _viewer_or_404(request)
    message = _find(viewer, pk)
    mark_read(viewer, message)

    session = active_session(request) if is_player(request) else None
    data = _row(message, False)
    data.update({
        "from": _sender(message),
        "to": message.to_login or "all",
        "body": message.body,
        "attachments": [payload(item, session) for item in message.attachments.all()],
    })
    return JsonResponse(data)


@require_POST
def message_unread(request, pk):
    viewer = _viewer_or_404(request)
    mark_unread(viewer, _find(viewer, pk))
    return JsonResponse({"unread": True})


@require_POST
def attachment_save(request, pk):
    """Сохранить файл вложения в файловую систему игрока (только вошедшему через Discord)."""
    viewer = _viewer_or_404(request)

    attachment = Attachment.objects.filter(pk=pk).select_related("machine_file", "message").first()
    if attachment is None or attachment.message_id not in {m.pk for m in visible_messages(viewer)}:
        raise Http404

    if not is_player(request):
        return JsonResponse({"error": AUTH_REQUIRED}, status=403)

    try:
        path = save_to_machine(active_session(request), attachment)
    except SaveError as error:
        return JsonResponse({"error": str(error)}, status=error.status)

    return JsonResponse({"saved": True, "path": path})
