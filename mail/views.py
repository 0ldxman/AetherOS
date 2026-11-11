"""Приложение «Почта» игрока: ящик учётки на машине (mail.boxes). Письмо называется своим путём в виде машины."""
import json
import re

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from mail.boxes import FOLDERS, box_for

PREVIEW_LENGTH = 90
PULSE_LIMIT = 20


def _box(request):
    box = box_for(request)
    if box is None:
        raise Http404
    return box


def _plain(text):
    """Текст без разметки письма (# - > ** * `): для превью в карточке."""
    text = re.sub(r"^\s*(#{1,3}\s+|[-*]\s+|>\s?)", "", text, flags=re.MULTILINE)
    return " ".join(re.sub(r"(\*\*|\*|`)", "", text).split())


def _when(row):
    if row.arrived is not None:
        return f"{row.arrived:%Y-%m-%d %H:%M}"
    return row.letter.get("Date")


def _row(row):
    body = _plain(row.letter.body[:PREVIEW_LENGTH * 6])
    return {
        "id": row.path, "folder": row.folder, "sender": row.letter.sender or "unknown", "subject": row.subject, "when": _when(row),
        "unread": row.folder == "inbox" and not row.read, "label": row.letter.get("X-Label"), "tone": row.letter.get("X-Label-Tone") or "dim",
        "preview": "" if row.locked else body[:PREVIEW_LENGTH] + ("…" if len(body) > PREVIEW_LENGTH else ""),
        "attachments": len(row.attachments), "locked": row.locked,
    }


def _path(request):
    data = request.GET if request.method == "GET" else json.loads(request.body or b"{}")
    path = (data.get("path") or "").strip()
    if not path:
        raise Http404
    return path


@ensure_csrf_cookie
def inbox(request):
    box = _box(request)
    return render(request, "mail/inbox.html", {"address": box.address, "file": request.GET.get("file", "")})


@require_GET
def message_list(request):
    box = _box(request)
    rows = [row for folder in FOLDERS for row in box.letters_in(folder)]
    return JsonResponse({"address": box.address, "messages": [_row(row) for row in rows]})


@require_GET
def pulse(request):
    """Что нового во входящих: рабочий стол опрашивает это ради бейджа и уведомления."""
    box = _box(request)
    fresh = [row for row in box.letters_in("inbox") if not row.read]
    return JsonResponse({"unread": len(fresh), "messages": [{"id": row.path, "sender": row.letter.sender, "subject": row.subject} for row in fresh[:PULSE_LIMIT]]})


@require_GET
def message_detail(request):
    """Письмо целиком. Открытие отмечает его прочитанным."""
    box = _box(request)
    row = box.letter(_path(request))
    if row is None:
        raise Http404
    box.mark(row.path, True)
    data = _row(row)
    data.update({
        "from": row.letter.sender, "to": row.letter.to, "body": row.letter.body,
        "headers": [[name, value] for name, value in row.letter.headers],
        "attachments": [{"kind": "member", "label": member.path, "path": f"{row.path}/{member.path}"} for member in row.attachments],
    })
    return JsonResponse(data)


@require_POST
def message_unread(request):
    box = _box(request)
    box.mark(_path(request), False)
    return JsonResponse({"ok": True})


@require_POST
def message_trash(request):
    box = _box(request)
    if box.user is None:
        return JsonResponse({"error": "sign in to manage mail"}, status=403)
    path = _path(request)
    if box.letter(path) is None:
        raise Http404
    folder = box.folder_of(path)
    target = box.restore(path) if folder == "trash" else box.trash(path)
    return JsonResponse({"path": target})
