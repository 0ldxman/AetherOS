"""Приложение «форум» у игрока: пространства машины, дерево разделов, темы, дерево ответов. Отдаёт JSON, страница одна (forum/static/forum/forum.js)."""
import json

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from filesystem import rights
from filesystem.machine_view.entries import BadName, Occupied, ReadOnly
from forum import attach, logic, reading
from forum.models import Attachment, Post, Section, Space, Topic


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


def _ago(moment):
    """Сколько прошло по игровому времени: «12 min», «3 h», «2 d»."""
    from machines.world import chrono
    from machines.world.dates import ago

    return ago(chrono.to_game(moment)) if moment else ""


def _face(row):
    """Код и цвет персонажа, если запись от него: бейдж тот же во всех каналах."""
    found = row.character
    return {"code": found.code, "color": found.color} if found is not None else {}


def _topic_row(request, topic, info):
    return {**_face(topic), "id": topic.pk, "title": topic.title, "name": topic.name, "kind": topic.kind, "pinned": topic.pinned, "locked": topic.locked,
            "excerpt": info["excerpt"], "replies": info["replies"], "new": info["new"], "unseen": info["unseen"],
            "at": _when(request, topic.created_at), "ago": _ago(topic.created_at),
            "last_name": info["last_name"], "last_ago": _ago(info["last_at"])}


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
        "node": machine.hostname if machine is not None else "",
        "callsign": logic.author_name(player) if player else "",
        "spaces": [{"slug": s.slug, "title": s.title, "about": s.about} for s in logic.spaces_for(machine, keys)],
    })


@require_GET
def space(request, slug):
    found = _space(request, slug)
    _, keys = _context(request)
    player = _player(request)

    topics = list(Topic.objects.filter(section__space=found, hidden_at__isnull=True))
    info = reading.summaries(topics, player)
    per_section = {}
    for item in topics:
        row = per_section.setdefault(item.section_id, {"topics": 0, "new": 0, "last": None})
        row["topics"] += 1
        data = info[item.pk]
        if data["new"] or data["unseen"]:
            row["new"] += 1
        if data["last_at"] and (row["last"] is None or data["last_at"] > row["last"][0]):
            row["last"] = (data["last_at"], item, data["last_name"])

    def summary(section):
        row = per_section.get(section.pk, {"topics": 0, "new": 0, "last": None})
        last = row["last"]
        return {"topics": row["topics"], "new": row["new"],
                "last": {"topic": last[1].pk, "title": last[1].title, "name": last[2], "ago": _ago(last[0])} if last else None}

    def convert(nodes):
        return [{"id": n["section"].pk, "title": n["section"].title, "about": n["section"].about, **summary(n["section"]),
                 "can_write": logic.can_write(n["section"], player, keys), "mine": logic.moderates(n["section"], player),
                 "children": convert(n["children"])} for n in nodes]

    tree = convert(logic.sections_of(found, keys))

    def ids(nodes):
        return {n["id"]: n["title"] for n in nodes} | {k: v for n in nodes for k, v in ids(n["children"]).items()}

    readable = ids(tree)
    recent = sorted((t for t in topics if t.section_id in readable), key=lambda t: info[t.pk]["last_at"] or t.created_at, reverse=True)[:8]
    return JsonResponse({"slug": found.slug, "title": found.title, "about": found.about, "tree": tree,
                         "can_create": logic.can_create(found, None, player, keys),
                         "recent": [{**_topic_row(request, t, info[t.pk]), "section": t.section_id, "section_title": readable[t.section_id]} for t in recent]})


@require_GET
def section(request, pk):
    found = _section(request, pk)
    _, keys = _context(request)
    player = _player(request)
    listed = list(logic.topics_in(found))
    info = reading.summaries(listed, player)
    topics = [_topic_row(request, t, info[t.pk]) for t in listed]
    return JsonResponse({"id": found.pk, "title": found.title, "about": found.about, "space": found.space.slug, "crumbs": _crumbs(found),
                         "can_write": logic.can_write(found, player, keys), "can_create": logic.can_create(found.space, found, player, keys),
                         "can_moderate": logic.moderates(found, player), "topics": topics})


@require_GET
def topic(request, pk):
    found = _topic(request, pk)
    _, keys = _context(request)
    player = _player(request)
    moderator = logic.moderates(found.section, player)
    fresh = reading.new_posts(found, player)
    reading.mark_seen(found, player)
    posts = [{"id": p.pk, "parent": p.parent_id, "root": p.root, "name": p.name, "kind": p.kind, "at": _when(request, p.created_at),
              "ago": _ago(p.created_at), "new": p.pk in fresh, **_face(p), "useful": p.useful, "starter": p.author_id is not None and p.author_id == found.author_id,
              "hidden": p.hidden_at is not None, "text": p.text if moderator or p.hidden_at is None else "",
              "files": [] if p.hidden_at is not None else [{"id": a.pk, "name": a.name, "size": a.size} for a in p.attachments.all()]}
             for p in logic.posts_of(found)]
    can = logic.can_write(found.section, player, keys) and not found.locked
    return JsonResponse({"id": found.pk, "title": found.title, "locked": found.locked, "pinned": found.pinned, "section": found.section_id,
                         "space": found.section.space.slug, "crumbs": _crumbs(found.section), "can_reply": can, "can_moderate": moderator,
                         "can_mark": logic.can_mark_useful(found, player), "posts": posts})


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _box(request):
    from mail.boxes import box_for

    box = box_for(request)
    if box is None:
        raise Http404
    return box


def _snapshots(request, data, keys):
    """Снимки файлов, которые игрок приложил (пути его вида машины): проверяются до создания записи."""
    paths = [str(path) for path in (data.get("attachments") or []) if path][:attach.MAX_PER_POST + 1]
    if not paths:
        return []
    if _player(request) is None:
        raise logic.ForumError("файлы прикладывают только игроки")
    from machines.access.groups import principal_for

    box = _box(request)
    principal = principal_for(box.profile) if box.profile is not None else None
    found = []
    for path in paths:
        entry = box.view.get(path)
        if entry is not None and principal is not None:
            try:
                rights.check(box.view, principal, entry.path, "r")
            except rights.Denied:
                raise logic.ForumError(f"{path}: нет доступа") from None
        found.append(attach.snapshot(entry, keys))
    return found


@require_GET
def files(request):
    """Папка машины игрока для выбора вложения: те же правила, что у вложений почты."""
    from machines.access.groups import principal_for
    from machines.world import places

    box = _box(request)
    if box.user is None:
        return _error("sign in to attach files", 403)
    path = request.GET.get("path")
    if not path:
        path = places.resolve(box.machine, "home", box.login) or "/"
        if not box.view.is_directory(path):                    # у записи может не быть домашней папки: тогда с корня
            path = "/"
    if not box.view.is_directory(path):
        raise Http404
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


@require_POST
def save_attachment(request):
    """Сохранить вложение на диск игрока: копия в его домашней папке."""
    found = Attachment.objects.select_related("post__topic__section__space", "post__topic__section__parent").filter(pk=_body(request).get("attachment")).first()
    if found is None or found.post.hidden_at is not None:
        raise Http404
    _topic(request, found.post.topic_id)
    try:
        path = attach.save_to_disk(_box(request), found)
    except logic.ForumError as error:
        return _error(error, 403)
    except (ReadOnly, Occupied, BadName, rights.Denied, rights.NotPermitted):
        return _error("cannot save the file here", 403)
    return JsonResponse({"path": path})


@require_POST
def new_topic(request):
    data = _body(request)
    found = _section(request, data.get("section"))
    _, keys = _context(request)
    try:
        snapshots = _snapshots(request, data, keys)
        created = logic.start_topic(found, _player(request), data.get("title"), data.get("text"), keys)
        attach.attach(created.posts.get(root=True), snapshots)
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
        snapshots = _snapshots(request, data, keys)
        created = logic.reply(found, _player(request), data.get("text"), keys, parent=parent)
        attach.attach(created, snapshots)
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"id": created.pk})


@require_POST
def new_section(request):
    data = _body(request)
    space = _space(request, data.get("space"))
    _, keys = _context(request)
    parent = _section(request, data["parent"]) if data.get("parent") else None
    try:
        created = logic.create_section(space, parent, _player(request), data.get("title"), data.get("about"), keys)
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"id": created.pk})


def _post_of(request, pk):
    """Сообщение для модерации: тема видна игроку, а раздел он вправе модерировать."""
    post = Post.objects.select_related("topic__section__space", "topic__section__parent").filter(pk=pk).first()
    if post is None:
        raise Http404
    _section(request, post.topic.section_id)
    return post


@require_POST
def hide_post(request):
    data = _body(request)
    post = _post_of(request, data.get("post"))
    try:
        logic.mod_hide(post, _player(request), str(data.get("reason") or ""))
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"ok": True})


@require_POST
def restore_post(request):
    post = _post_of(request, _body(request).get("post"))
    try:
        logic.mod_restore(post, _player(request))
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"ok": True})


@require_POST
def topic_flags(request):
    data = _body(request)
    found = _topic(request, data.get("topic"))
    try:
        logic.mod_flags(found, _player(request), pinned=data.get("pinned"), locked=data.get("locked"))
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"ok": True})


@require_POST
def archive_section(request):
    found = _section(request, _body(request).get("section"))
    try:
        logic.mod_archive(found, _player(request))
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"ok": True})


@require_POST
def useful(request):
    """Автор темы отмечает ответ полезным (или снимает отметку)."""
    data = _body(request)
    post = _post_of(request, data.get("post"))
    try:
        logic.mark_useful(post, _player(request), bool(data.get("on", True)))
    except logic.ForumError as error:
        return _error(error, 403)
    return JsonResponse({"ok": True})
