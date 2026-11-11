"""Приложение support у игрока: свои обращения, переписка с командой, вложения."""
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from support import desk
from support.models import Ticket


def _player(request):
    if not request.user.is_authenticated:
        raise Http404
    return request.user


def _ticket(request, ticket_id):
    found = Ticket.objects.filter(pk=ticket_id, user=_player(request)).first()
    if found is None:
        raise Http404
    return found


def _error(error):
    messages = [text for texts in getattr(error, "message_dict", {"": error.messages}).values() for text in texts]
    return JsonResponse({"error": " ".join(messages)}, status=400)


@ensure_csrf_cookie
def index(request):
    return render(request, "support/index.html", {"guest": not request.user.is_authenticated,
                                                  "limits": {"files": desk.MAX_FILES, "size": desk.MAX_SIZE}})


@require_GET
def tickets(request):
    user = _player(request)
    return JsonResponse({"tickets": [{
        "id": t.pk, "subject": t.subject, "category": t.category, "status": t.status, "when": f"{t.updated_at:%Y-%m-%d %H:%M}",
        "unread": desk.unread_for(t),
    } for t in Ticket.objects.filter(user=user)]})


def _file(f):
    return {"id": f.pk, "name": f.name, "size": f.size, "image": desk.inline(f),
            "url": reverse("support:file", args=[f.pk])}


@require_GET
def ticket(request, ticket_id):
    found = _ticket(request, ticket_id)
    desk.seen(found)
    name = desk.responder(found)
    return JsonResponse({
        "id": found.pk, "subject": found.subject, "category": found.category, "status": found.status, "responder": name,
        "messages": [{"id": m.pk, "staff": m.staff, "author": name if m.staff else "you", "text": m.text,
                      "when": f"{m.created_at:%Y-%m-%d %H:%M}", "files": [_file(f) for f in m.files.all()]} for m in desk.visible(found)],
    })


@require_POST
def create(request):
    try:
        found = desk.open_ticket(_player(request), subject=request.POST.get("subject", ""), category=request.POST.get("category", ""),
                                 text=request.POST.get("text", ""), uploads=request.FILES.getlist("files"), context=desk.context_of(request))
    except ValidationError as error:
        return _error(error)
    return JsonResponse({"id": found.pk})


@require_POST
def reply(request, ticket_id):
    found = _ticket(request, ticket_id)
    try:
        desk.player_reply(found, request.user, request.POST.get("text", ""), request.FILES.getlist("files"))
    except ValidationError as error:
        return _error(error)
    return JsonResponse({"ok": True})


@require_GET
def file(request, file_id):
    found = desk.file_of(file_id, user=_player(request))
    if found is None:
        raise Http404
    response = HttpResponse(bytes(found.data), content_type=found.content_type or "application/octet-stream")
    mode = "inline" if desk.inline(found) else "attachment"
    response["Content-Disposition"] = f'{mode}; filename="{found.name.replace(chr(34), "")}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def pulse(request):
    if not request.user.is_authenticated:
        return JsonResponse({"unread": 0, "items": []})
    return JsonResponse(desk.pulse(request.user))
