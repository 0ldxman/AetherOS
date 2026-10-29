"""Вьювер raw для файлов файловой системы: те же байты, что показывают blk и txtx, в окне с hex, строками и поиском.

Окно открывает cnt -r. Содержимое отдаётся диапазонами (HTTP Range), как у ассетов: вьювер читает файл кусками.
"""
import hashlib
import posixpath
import re
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.csrf import ensure_csrf_cookie

from filesystem.content.rawview import build_raw_cached, viewer_formats
from machines.network.bridge import terminal_session
from terminal.engine.context import TerminalContext
from terminal.engine.filesystem import VirtualFilesystem
from users.aether_auth import is_player
from secure.requestkeys import request_keys

RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _entry(request):
    """Файл игрока по ?path=: его сессия, его слои, его ключи. Чужих и несуществующих путей нет."""
    if not is_player(request):
        raise PermissionDenied

    session = terminal_session(request)
    context = TerminalContext(session=session, cwd="/home", request=request)
    path = posixpath.normpath("/" + request.GET.get("path", "").lstrip("/"))
    fs = VirtualFilesystem(context)
    entry = fs.get_file(path)
    if entry is None or fs.is_directory(path):
        raise Http404
    return entry, context


def edit_url(path):
    return reverse("fsview:edit") + "?" + urlencode({"path": path})


def raw_url(path):
    return reverse("fsview:raw") + "?" + urlencode({"path": path})


def raw_page(request):
    entry, _ = _entry(request)
    name = posixpath.basename(entry.path)
    identity = hashlib.sha1(f"{terminal_session(request).pk}:{entry.path}".encode()).hexdigest()[:12]
    content = reverse("fsview:content") + "?" + urlencode({"path": entry.path})
    return render(
        request,
        "assets/viewers/raw.html",
        {"asset": SimpleNamespace(name=name, public_id=identity), "content_url": content, "formats_json": viewer_formats()},
    )


def raw_content(request):
    entry, context = _entry(request)
    from mail.access import viewer_for

    data = build_raw_cached(entry, context.view, request_keys(request), viewer=viewer_for(request))
    total = len(data)

    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store", "Content-Type": "application/octet-stream"}
    if request.method == "HEAD":
        response = HttpResponse(status=200, headers=headers)
        response["Content-Length"] = str(total)
        return response

    header = request.headers.get("Range")
    if not header:
        return HttpResponse(data, status=200, headers=headers)

    found = RANGE.match(header.strip())
    if not found or (found.group(1) == "" and found.group(2) == ""):
        return HttpResponse(status=416, headers={"Content-Range": f"bytes */{total}"})

    if found.group(1) == "":                                  # bytes=-N: последние N байт
        start, end = max(0, total - int(found.group(2))), total - 1
    else:
        start = int(found.group(1))
        end = min(int(found.group(2)), total - 1) if found.group(2) else total - 1

    if start >= total or start > end:
        return HttpResponse(status=416, headers={"Content-Range": f"bytes */{total}"})

    response = HttpResponse(data[start:end + 1], status=206, headers=headers)
    response["Content-Range"] = f"bytes {start}-{end}/{total}"
    return response


def text_content(request):
    """Содержимое файла как текст (cnt): те же байты, что в raw, но в простом окне."""
    entry, context = _entry(request)
    from mail.access import viewer_for

    data = build_raw_cached(entry, context.view, request_keys(request), viewer=viewer_for(request))
    return HttpResponse(data.decode("utf-8", "replace"), content_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store"})


EDIT_LIMIT = 200_000


@ensure_csrf_cookie        # страница сама токена не печатает, а сохранение шлёт его из куки
def edit_page(request):
    """Редактор текста файла (edt): тот же вьювер, но с правкой. GET отдаёт страницу, POST сохраняет правку в слой игрока."""
    import json

    from django.http import JsonResponse

    from filesystem import edit, rights

    entry, context = _entry(request)
    reason = edit.refusal(entry)
    if reason:
        return JsonResponse({"ok": False, "error": reason}, status=400) if request.method == "POST" else HttpResponse(reason, status=400)
    try:
        context.require(entry.path, "r" if request.method == "GET" else "w")
    except rights.Denied:
        return JsonResponse({"ok": False, "error": "Permission denied"}, status=403) if request.method == "POST" else HttpResponse("Permission denied", status=403)

    if request.method == "POST":
        try:
            text = json.loads(request.body or b"{}").get("text")
        except ValueError:
            text = None
        if not isinstance(text, str) or len(text) > EDIT_LIMIT:
            return JsonResponse({"ok": False, "error": "Bad text"}, status=400)
        context.view.edit_text(entry.path, text)
        return JsonResponse({"ok": True})

    name = posixpath.basename(entry.path)
    identity = hashlib.sha1(f"{terminal_session(request).pk}:{entry.path}".encode()).hexdigest()[:12]
    return render(request, "filesystem/edit.html", {
        "asset": SimpleNamespace(name=name, public_id=identity), "text": entry.body,
        "save_url": reverse("fsview:edit") + "?" + urlencode({"path": entry.path}),
    })
