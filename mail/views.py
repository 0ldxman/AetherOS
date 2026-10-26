import json
import re
from datetime import timezone

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from machines.current import active_session
from users.aether_auth import AUTH_REQUIRED, is_player

from .access import mark_read, mark_unread, read_ids, viewer_for, visible_messages
from .addresses import split
from .attachments import SaveError, payload, save_to_machine
from .compose import TaskError, available_tasks, public_segments, send
from .models import Attachment, ComposeProgress

PREVIEW_LENGTH = 90


def _when(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _plain(text):
    """Текст без разметки письма (# - > ** * `): для превью в карточке."""
    text = re.sub(r"^\s*(#{1,3}\s+|[-*]\s+|>\s?)", "", text, flags=re.MULTILINE)
    return " ".join(re.sub(r"(\*\*|\*|`)", "", text).split())


def _row(message, unread):
    body = _plain(message.body)
    return {
        "id": message.pk,
        "sender": message.sender,
        "subject": message.subject or "(no subject)",
        "when": _when(message.sent_at),
        "unread": unread,
        "folder": getattr(message, "folder", "inbox"),
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


PULSE_LIMIT = 20


@require_GET
def pulse(request):
    """Что нового во входящих: рабочий стол опрашивает это ради бейджа и уведомления."""
    viewer = _viewer_or_404(request)
    done = read_ids(viewer)
    fresh = [m for m in visible_messages(viewer, "inbox") if m.pk not in done]
    return JsonResponse({
        "unread": len(fresh),
        "messages": [
            {"id": m.pk, "sender": m.sender, "subject": m.subject or "(no subject)"}
            for m in fresh[:PULSE_LIMIT]
        ],
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
        "from": message.sender,
        "to": ", ".join(split(message.recipients)),
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


@require_GET
def task_list(request):
    """Задачи на набор, доступные игроку на этом ящике (только вошедшему через Discord)."""
    viewer = _viewer_or_404(request)

    if not is_player(request):
        return JsonResponse({"error": AUTH_REQUIRED}, status=403)

    tasks = available_tasks(viewer)
    used = dict(
        ComposeProgress.objects.filter(user=viewer.user, task__in=tasks).values_list("task_id", "attempts")
    )

    return JsonResponse({
        "from": viewer.address,
        "tasks": [
            {
                "id": task.pk,
                "to": ", ".join(split(task.recipients)),
                "subject": task.subject,
                "segments": public_segments(task),
                "attempts_left": (
                    max(0, task.max_attempts - used.get(task.pk, 0)) if task.max_attempts else None
                ),
            }
            for task in tasks
        ],
    })


@require_POST
def task_send(request, pk):
    """Отправить набранный текст. Сервер сам сверяет его с целевым."""
    viewer = _viewer_or_404(request)

    if not is_player(request):
        return JsonResponse({"error": AUTH_REQUIRED}, status=403)

    task = next((t for t in available_tasks(viewer) if t.pk == pk), None)
    if task is None:
        raise Http404

    try:
        payload_in = json.loads(request.body)
        text = payload_in["text"]
        if not isinstance(text, str) or len(text) > 20000:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "invalid message"}, status=400)

    try:
        send(request.user, task, text)
    except TaskError as error:
        return JsonResponse({"error": str(error), **error.extra}, status=error.status)

    return JsonResponse({"sent": True})
