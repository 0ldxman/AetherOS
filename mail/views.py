"""Приложение «Почта» игрока: ящик учётки на машине (mail.boxes). Письмо называется своим путём в виде машины."""
import json
import re

from urllib.parse import urlencode

from django.http import Http404, JsonResponse
from django.urls import reverse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from mail.boxes import FOLDERS, box_for

PREVIEW_LENGTH = 90
PULSE_LIMIT = 20


def _box(request):
    from world.letters import deliver

    box = box_for(request)
    if box is None:
        raise Http404
    deliver(box, _keys(request))    # письма мира всем: приходят при открытии почты (с условием — тем, чьи ключи подходят)
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
        "attachments": [{"kind": "member", "label": member.path, "path": f"{row.path}/{member.path}",
                         "open": reverse("mail:attachment") + "?" + urlencode({"path": f"{row.path}/{member.path}"})} for member in row.attachments],
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


# ---- ответ, новое письмо, пересылка (mail.talk) ---------------------------------------------------------------------------

def _keys(request):
    from secure.requestkeys import request_keys

    return request_keys(request)


def _offer(offer):
    from mail.talk import public

    variant = offer.variant
    if not offer.open:
        return {"id": variant.pk, "title": "???", "open": False, "segments": [], "attach": False}
    return {"id": variant.pk, "title": variant.title, "open": True, "segments": public(variant.text) if variant.text.strip() else [],
            "attach": bool(variant.attachment)}


def _letter_item(box, path):
    entry = box.view.get(path) if path else None
    return entry.item if entry is not None else None


@require_GET
def compose_options(request):
    """Что игрок может написать: ответ на письмо (reply=путь), новое письмо (to=адрес) или пересылку (forward=путь, to=адрес)."""
    from mail import talk

    box = _box(request)
    if box.user is None:
        return JsonResponse({"error": "sign in to send mail"}, status=403)
    keys = _keys(request)
    reply, forward, to = request.GET.get("reply", ""), request.GET.get("forward", ""), request.GET.get("to", "").strip()
    subject, offers, persona = "", [], None
    if reply:
        row = box.letter(reply)
        if row is None:
            raise Http404
        to = to or row.letter.sender
        subject = row.letter.subject if row.letter.subject.lower().startswith("re:") else f"Re: {row.letter.subject}"
        persona, offers = talk.offers_for_reply(box.user, box.profile, keys, _letter_item(box, reply))
        if not offers:
            persona, offers = talk.offers_for_address(box.user, box.profile, keys, to)
    elif forward:
        row = box.letter(forward)
        if row is None:
            raise Http404
        subject = f"Fwd: {row.letter.subject}"
        if to:
            persona, offers = talk.offers_for_forward(box.user, box.profile, keys, to, _letter_item(box, forward))
    elif to:
        persona, offers = talk.offers_for_address(box.user, box.profile, keys, to)
    return JsonResponse({
        "from": box.address, "to": to, "subject": subject,
        "persona": {"address": persona.address, "name": persona.name} if persona else None,
        "offers": [_offer(offer) for offer in offers],
    })


def _browser_effects(effects):
    from django.urls import get_script_prefix

    out = []
    for effect in effects:
        if effect.get("op") == "open":
            url = get_script_prefix().rstrip("/") + "/" + effect["url"]
            out.append({**effect, "url": url, "id": "hook-" + re.sub(r"\W+", "-", effect["url"]).strip("-")})
        else:
            out.append(effect)
    return out


@require_POST
def send_letter(request):
    """Отправить письмо: вариант набран (сверяет сервер), вложение по пути, ответ или пересылка письма ящика."""
    from mail import talk
    from mail.models import Variant

    box = _box(request)
    if box.user is None:
        return JsonResponse({"error": "sign in to send mail"}, status=403)
    data = json.loads(request.body or b"{}")
    variant = Variant.objects.select_related("step__conversation").filter(pk=data.get("variant")).first() if data.get("variant") else None
    attachment = None
    if data.get("attachment"):
        attachment = box.view.get(str(data["attachment"]))
        if attachment is None or attachment.is_dir:
            return JsonResponse({"error": "no such file to attach"}, status=400)
    reply_item = _letter_item(box, data.get("reply", "")) if data.get("reply") else None
    forward_item = _letter_item(box, data.get("forward", "")) if data.get("forward") else None
    if data.get("forward") and forward_item is None and box.letter(data["forward"]) is None:
        raise Http404
    result = talk.send(box, _keys(request), to=data.get("to", ""), subject=data.get("subject", ""), typed=data.get("text", ""),
                       variant=variant, attachment=attachment, reply_item=reply_item, forward_item=forward_item)
    status = 400 if result.kind in ("mismatch", "closed") else 200
    return JsonResponse({"kind": result.kind, "path": result.path, "left": result.left, "effects": _browser_effects(result.effects),
                         "error": result.detail if status == 400 else ""}, status=status)


@require_GET
def files(request):
    """Папка машины игрока для выбора вложения: папки и файлы, которые он вправе читать."""
    from filesystem import rights

    box = _box(request)
    if box.user is None:
        return JsonResponse({"error": "sign in to send mail"}, status=403)
    from machines.world import places

    path = request.GET.get("path") or places.resolve(box.machine, "home", box.login) or "/"
    if not box.view.is_directory(path):
        raise Http404
    from machines.access.groups import principal_for

    principal = principal_for(box.profile) if box.profile is not None else None
    rows = []
    for entry in box.view.children(path):
        if entry.hidden:
            continue
        if principal is not None:
            try:
                rights.check(box.view, principal, entry.path, "r")
            except rights.Denied:
                continue
        rows.append({"name": entry.name, "path": entry.path, "dir": entry.is_dir})
    rows.sort(key=lambda row: (not row["dir"], row["name"].lower()))
    parent = (path.rsplit("/", 1)[0] or "/") if path != "/" else ""
    return JsonResponse({"path": path, "parent": parent, "entries": rows})


@require_GET
def attachment(request):
    """Открыть вложение письма из ящика: окно по виду содержимого, как cnt в терминале (закрытое слоями не откроется)."""
    from filesystem.content.window import resolve_content

    box = _box(request)
    path = (request.GET.get("path") or "").rstrip("/")
    entry = box.attachment(path)
    if entry is None:
        raise Http404
    name = path.rsplit("/", 1)[-1]
    content = resolve_content(entry, path, name, {"mail": path})
    if content.error == "locked":
        return JsonResponse({"error": f"{name}: content is locked"}, status=403)
    if content.error or not content.url:
        return JsonResponse({"error": f"{name}: no content"}, status=400)
    return JsonResponse({"id": "mail-" + re.sub(r"\W+", "-", path).strip("-"), "title": name, "url": content.url})
