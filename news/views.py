"""Приложение news у игрока: лента объявлений команды."""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from news import feed


@ensure_csrf_cookie
def index(request):
    return render(request, "news/index.html")


@require_GET
def posts(request):
    rows = feed.feed(request.user)
    return JsonResponse({"posts": [{
        "id": post.pk, "title": post.title, "body": post.body, "when": f"{post.publish_at:%Y-%m-%d %H:%M}",
        "pinned": post.pinned, "important": post.important, "unread": not read,
        "author": post.author.get_username() if post.author_id else "",
    } for post, read in rows], "guest": not request.user.is_authenticated})


@require_POST
def read(request):
    data = json.loads(request.body or b"{}")
    ids = [int(i) for i in data.get("ids", []) if str(i).isdigit()]
    return JsonResponse({"marked": feed.mark_read(request.user, ids)})


@require_GET
def pulse(request):
    return JsonResponse(feed.pulse(request.user))
