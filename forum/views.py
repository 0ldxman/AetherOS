"""Приложение «форум» у игрока: пространства машины, дерево разделов, темы, дерево ответов. Отдаёт JSON, страница одна (forum/static/forum/forum.js)."""
import json

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from forum import logic
from forum.models import Post, Section, Space, Topic


def _context(request):
    from machines.current import current_machine
    from secure.requestkeys import request_keys

    return current_machine(request), request_keys(request)


def _player(request):
    return request.user if request.user.is_authenticated else None


def _space(request, slug):
    """Пространство, которое видит игрок на этой машине, или 404."""
    machine, keys = _context(request)
    for space in logic.spaces_for(machine, keys):
        if space.slug == slug:
            return space
    raise Http404


def _section(request, pk):
    machine, keys = _context(request)
    try:
        section = Section.objects.select_related("space", "parent").get(pk=pk, archived=False)
    except Section.DoesNotExist:
        raise Http404 from None
    _space(request, section.space.slug)
    if not logic.can_read(section, keys):
        raise Http404
    return section


def _topic(request, pk):
    try:
        topic = Topic.objects.select_related("section__space", "section__parent").get(pk=pk, hidden_at__isnull=True)
    except Topic.DoesNotExist:
        raise Http404 from None
    _section(request, topic.section_id)
    return topic


def _when(request, moment):
    from machines.world import chrono

    machine, _ = _context(request)
    return chrono.stamp(moment, machine, "%Y-%m-%d %H:%M")


def _error(error, status=400):
    return JsonResponse({"error": str(error)}, status=status)


def _crumbs(section):
    return [{"id": item.pk, "title": item.title} for item in logic._chain(section)]


@ensure_csrf_cookie
def index(request):
    return render(request, "forum/index.html")


@require_GET
def spaces(request):
    machine, keys = _context(request)
    player = _player(request)
    return JsonResponse({
        "callsign": logic.author_name(player) if player else "",
        "spaces": [{"slug": s.slug, "title": s.title, "about": s.about} for s in logic.spaces_for(machine, keys)],
    })


@require_GET
def space(request, slug):
    found = _space(request, slug)
    _, keys = _context(request)
    player = _player(request)

    def convert(nodes):
        return [{"id": n["section"].pk, "title": n["section"].title, "about": n["section"].about,
                 "can_write": logic.can_write(n["section"], player, keys), "children": convert(n["children"])} for n in nodes]

    return JsonResponse({"slug": found.slug, "title": found.title, "about": found.about, "tree": convert(logic.sections_of(found, keys))})


@require_GET
def section(request, pk):
    found = _section(request, pk)
    _, keys = _context(request)
    topics = [{"id": t.pk, "title": t.title, "name": t.name, "kind": t.kind, "replies": t.replies, "pinned": t.pinned, "locked": t.locked,
               "at": _when(request, t.created_at), "last": _when(request, t.bumped_at)} for t in logic.topics_in(found)]
    return JsonResponse({"id": found.pk, "title": found.title, "about": found.about, "space": found.space.slug, "crumbs": _crumbs(found),
                         "can_write": logic.can_write(found, _player(request), keys), "topics": topics})


@require_GET
def topic(request, pk):
    found = _topic(request, pk)
    _, keys = _context(request)
    posts = [{"id": p.pk, "parent": p.parent_id, "root": p.root, "name": p.name, "kind": p.kind, "at": _when(request, p.created_at),
              "hidden": p.hidden_at is not None, "text": "" if p.hidden_at is not None else p.text} for p in logic.posts_of(found)]
    can = logic.can_write(found.section, _player(request), keys) and not found.locked
    return JsonResponse({"id": found.pk, "title": found.title, "locked": found.locked, "pinned": found.pinned, "section": found.section_id,
                         "space": found.section.space.slug, "crumbs": _crumbs(found.section), "can_reply": can, "posts": posts})


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@require_POST
def new_topic(request):
    data = _body(request)
    found = _section(request, data.get("section"))
    _, keys = _context(request)
    try:
        created = logic.start_topic(found, _player(request), data.get("title"), data.get("text"), keys)
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"id": created.pk})


@require_POST
def new_post(request):
    data = _body(request)
    found = _topic(request, data.get("topic"))
    _, keys = _context(request)
    parent = Post.objects.filter(pk=data["parent"], topic=found).first() if data.get("parent") else None
    try:
        created = logic.reply(found, _player(request), data.get("text"), keys, parent=parent)
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"id": created.pk})
