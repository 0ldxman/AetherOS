from datetime import timezone

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import get_script_prefix
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .access import mark_read, mark_unread, read_ids, viewer_for, visible_messages

PREVIEW_LENGTH = 90


def _when(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _sender(message):
    if message.sender_address:
        return f"{message.sender_name} <{message.sender_address}>"
    return message.sender_name


def _row(message, unread):
    body = " ".join(message.body.split())
    return {
        "id": message.pk,
        "sender": message.sender_name,
        "subject": message.subject or "(no subject)",
        "when": _when(message.sent_at),
        "unread": unread,
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
    return render(request, "mail/inbox.html", {
        "address": f"{viewer.login}@{viewer.machine.label}",
    })


@require_GET
def message_list(request):
    viewer = _viewer_or_404(request)
    done = read_ids(viewer)
    messages = visible_messages(viewer)
    return JsonResponse({"messages": [_row(m, m.pk not in done) for m in messages]})


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

    prefix = get_script_prefix().rstrip("/")
    data = _row(message, False)
    data.update({
        "from": _sender(message),
        "to": message.to_login or "all",
        "body": message.body,
        "attachments": [
            {"label": item.label, "url": prefix + item.path}
            for item in message.attachments.all()
        ],
    })
    return JsonResponse(data)


@require_POST
def message_unread(request, pk):
    viewer = _viewer_or_404(request)
    mark_unread(viewer, _find(viewer, pk))
    return JsonResponse({"unread": True})
