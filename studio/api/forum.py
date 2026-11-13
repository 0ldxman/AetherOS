"""Форум в Студии: пространства с привязкой машин, дерево разделов, модерация и голос персонажа. Логика в forum/logic.py."""
import datetime as dt
import re

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from documents.markup.expr import SpoilerSyntaxError, parse_expr
from forum import logic
from forum.models import Kind, Post, Section, Space, Topic
from machines.models import Machine
from secure.access import format_condition

router = Router(tags=["forum"])

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")


class FoErrors(Schema):
    fields: dict[str, str]


class FoMachine(Schema):
    id: int
    label: str
    hostname: str


class FoSpaceRow(Schema):
    slug: str
    title: str
    sections: int
    topics: int
    machines: int
    authors_only: bool


class FoSection(Schema):
    id: int
    parent: int | None
    title: str
    about: str
    order: int
    read_if: str
    write: str
    write_if: str
    create: str
    create_if: str
    created_by: str              # логин игрока, если раздел создал игрок
    archived: bool
    topics: int


class FoSpaceOut(Schema):
    slug: str
    title: str
    about: str
    order: int
    read_if: str
    write: str
    write_if: str
    create: str
    create_if: str
    machines: list[int]
    machine_options: list[FoMachine]
    sections: list[FoSection]


class FoSpaceIn(Schema):
    slug: str = ""
    title: str
    about: str = ""
    order: int = 0
    read_if: str = ""
    write: str = "players"
    write_if: str = ""
    create: str = "players"
    create_if: str = ""
    machines: list[int] = []


class FoSectionIn(Schema):
    title: str
    parent: int | None = None
    about: str = ""
    order: int = 0
    read_if: str = ""
    write: str = "inherit"
    write_if: str = ""
    create: str = "inherit"
    create_if: str = ""
    archived: bool = False


class FoTopicRow(Schema):
    id: int
    title: str
    section: int
    section_title: str
    name: str
    kind: str
    replies: int
    pinned: bool
    locked: bool
    hidden: bool
    created_at: dt.datetime
    bumped_at: dt.datetime


class FoPost(Schema):
    id: int
    parent: int | None
    root: bool
    name: str
    kind: str
    player: str                  # логин игрока, если писал игрок
    text: str
    hidden: bool
    hidden_reason: str
    created_at: dt.datetime


class FoTopicOut(FoTopicRow):
    posts: list[FoPost]


class FoFlags(Schema):
    pinned: bool | None = None
    locked: bool | None = None


class FoAuthorTopic(Schema):
    section: int
    name: str
    title: str
    text: str
    kind: str = "character"


class FoAuthorPost(Schema):
    name: str
    text: str
    kind: str = "character"
    parent: int | None = None


class FoHide(Schema):
    reason: str = ""


# ---- условия: в Студии текстом, в базе деревом ----

def _cond(value):
    return format_condition(value) if value else ""


def _parse(text, field, errors):
    if not (text or "").strip():
        return None
    try:
        return parse_expr(text)
    except SpoilerSyntaxError as error:
        errors[field] = str(error)
        return None


def _bad(errors):
    return 400, {"fields": errors}


def _section_row(row, counts):
    return FoSection(id=row.pk, parent=row.parent_id, title=row.title, about=row.about, order=row.order, read_if=_cond(row.read_if),
                     write=row.write, write_if=_cond(row.write_if), create=row.create, create_if=_cond(row.create_if),
                     created_by=row.created_by.get_username() if row.created_by_id else "", archived=row.archived, topics=counts.get(row.pk, 0))


def _space_out(space):
    counts = dict(Topic.objects.filter(section__space=space).values_list("section").annotate(n=Count("id")))
    sections = Section.objects.filter(space=space).select_related("created_by")
    return FoSpaceOut(slug=space.slug, title=space.title, about=space.about, order=space.order, read_if=_cond(space.read_if), write=space.write,
                      write_if=_cond(space.write_if), create=space.create, create_if=_cond(space.create_if), machines=list(space.machines.values_list("pk", flat=True)),
                      machine_options=[FoMachine(id=m.pk, label=m.label, hostname=m.hostname) for m in Machine.objects.order_by("hostname")],
                      sections=[_section_row(row, counts) for row in sections])


def _apply_space(space, body, errors):
    title = body.title.strip()
    if not title:
        errors["title"] = "Нужно название."
    if body.write not in ("players", "authors"):
        errors["write"] = "Режим записи: players или authors."
    if body.create not in ("players", "authors"):
        errors["create"] = "Режим создания разделов: players или authors."
    read_if, write_if = _parse(body.read_if, "read_if", errors), _parse(body.write_if, "write_if", errors)
    create_if = _parse(body.create_if, "create_if", errors)
    if errors:
        return False
    space.title, space.about, space.order = title[:120], body.about, body.order
    space.read_if, space.write, space.write_if = read_if, body.write, write_if
    space.create, space.create_if = body.create, create_if
    space.save()
    space.machines.set(Machine.objects.filter(pk__in=body.machines))
    return True


# ---- пространства ----

@router.get("/spaces", response=list[FoSpaceRow])
def spaces(request):
    found = Space.objects.annotate(sections_n=Count("sections", distinct=True), machines_n=Count("machines", distinct=True))
    topics = dict(Topic.objects.values_list("section__space").annotate(n=Count("id")))
    return [FoSpaceRow(slug=s.slug, title=s.title, sections=s.sections_n, topics=topics.get(s.pk, 0), machines=s.machines_n, authors_only=s.write == "authors")
            for s in found]


@router.post("/spaces", response={200: FoSpaceOut, 400: FoErrors})
def create_space(request, body: FoSpaceIn):
    errors = {}
    slug = body.slug.strip().lower()
    if not _SLUG.match(slug):
        errors["slug"] = "Адрес: латиница, цифры и дефис, от 2 до 48 знаков."
    elif Space.objects.filter(slug=slug).exists():
        errors["slug"] = "Такой адрес уже занят."
    space = Space(slug=slug)
    if not _apply_space(space, body, errors):
        return _bad(errors)
    return _space_out(space)


@router.get("/spaces/{slug}", response=FoSpaceOut)
def space_detail(request, slug: str):
    return _space_out(get_object_or_404(Space, slug=slug))


@router.put("/spaces/{slug}", response={200: FoSpaceOut, 400: FoErrors})
def update_space(request, slug: str, body: FoSpaceIn):
    space, errors = get_object_or_404(Space, slug=slug), {}
    if not _apply_space(space, body, errors):
        return _bad(errors)
    return _space_out(space)


@router.delete("/spaces/{slug}", response={204: None})
def delete_space(request, slug: str):
    get_object_or_404(Space, slug=slug).delete()
    return 204, None


# ---- разделы ----

def _apply_section(section, space, body, errors):
    title = body.title.strip()
    if not title:
        errors["title"] = "Нужно название."
    if body.write not in ("inherit", "players", "authors"):
        errors["write"] = "Режим записи: inherit, players или authors."
    if body.create not in ("inherit", "players", "authors"):
        errors["create"] = "Режим создания: inherit, players или authors."
    parent = None
    if body.parent is not None:
        parent = Section.objects.filter(pk=body.parent, space=space).first()
        if parent is None:
            errors["parent"] = "Родитель из другого пространства."
        elif section.pk and any(item.pk == section.pk for item in logic._chain(parent)):
            errors["parent"] = "Раздел нельзя вложить в самого себя."
    read_if, write_if = _parse(body.read_if, "read_if", errors), _parse(body.write_if, "write_if", errors)
    create_if = _parse(body.create_if, "create_if", errors)
    if errors:
        return False
    section.create, section.create_if = body.create, create_if
    section.space, section.parent, section.title, section.about = space, parent, title[:120], body.about[:240]
    section.order, section.read_if, section.write, section.write_if, section.archived = body.order, read_if, body.write, write_if, body.archived
    section.save()
    return True


@router.post("/spaces/{slug}/sections", response={200: FoSection, 400: FoErrors})
def create_section(request, slug: str, body: FoSectionIn):
    space, errors, section = get_object_or_404(Space, slug=slug), {}, Section()
    if not _apply_section(section, space, body, errors):
        return _bad(errors)
    return _section_row(section, {})


@router.put("/sections/{section_id}", response={200: FoSection, 400: FoErrors})
def update_section(request, section_id: int, body: FoSectionIn):
    section, errors = get_object_or_404(Section, pk=section_id), {}
    if not _apply_section(section, section.space, body, errors):
        return _bad(errors)
    return _section_row(section, {section.pk: section.topics.count()})


@router.delete("/sections/{section_id}", response={204: None})
def delete_section(request, section_id: int):
    get_object_or_404(Section, pk=section_id).delete()
    return 204, None


# ---- темы и сообщения ----

def _topic_row(topic, replies):
    return dict(id=topic.pk, title=topic.title, section=topic.section_id, section_title=topic.section.title, name=topic.name, kind=topic.kind,
                replies=replies, pinned=topic.pinned, locked=topic.locked, hidden=topic.hidden_at is not None, created_at=topic.created_at,
                bumped_at=topic.bumped_at)


@router.get("/spaces/{slug}/topics", response=list[FoTopicRow])
def topics(request, slug: str, section: int | None = None, hidden: bool = False, q: str = ""):
    space = get_object_or_404(Space, slug=slug)
    found = Topic.objects.filter(section__space=space).select_related("section").annotate(n=Count("posts", filter=Q(posts__root=False)))
    if section:
        found = found.filter(section_id=section)
    found = found.filter(hidden_at__isnull=False) if hidden else found.filter(hidden_at__isnull=True)
    if q.strip():
        found = found.filter(Q(title__icontains=q.strip()) | Q(posts__text__icontains=q.strip())).distinct()
    return [FoTopicRow(**_topic_row(t, t.n)) for t in found.order_by("-pinned", "-bumped_at")[:200]]


def _post(post):
    return FoPost(id=post.pk, parent=post.parent_id, root=post.root, name=post.name, kind=post.kind,
                  player=post.author.get_username() if post.author_id else "", text=post.text, hidden=post.hidden_at is not None,
                  hidden_reason=post.hidden_reason, created_at=post.created_at)


def _topic_out(topic):
    posts = logic.posts_of(topic)
    return FoTopicOut(**_topic_row(topic, sum(1 for p in posts if not p.root)), posts=[_post(p) for p in posts])


@router.get("/topics/{topic_id}", response=FoTopicOut)
def topic_detail(request, topic_id: int):
    return _topic_out(get_object_or_404(Topic.objects.select_related("section"), pk=topic_id))


@router.put("/topics/{topic_id}", response=FoTopicOut)
def topic_flags(request, topic_id: int, body: FoFlags):
    topic = get_object_or_404(Topic.objects.select_related("section"), pk=topic_id)
    logic.set_flags(topic, pinned=body.pinned, locked=body.locked)
    topic.refresh_from_db()
    return _topic_out(topic)


def _author_kind(kind):
    return kind if kind in (Kind.CHARACTER, Kind.SYSTEM) else Kind.CHARACTER


@router.post("/topics", response={200: FoTopicOut, 400: FoErrors})
def author_topic(request, body: FoAuthorTopic):
    section = get_object_or_404(Section, pk=body.section)
    name = body.name.strip()[:16]
    if not name:
        return _bad({"name": "Нужна подпись персонажа."})
    try:
        topic = logic.author_topic(section, name, body.title, body.text, _author_kind(body.kind))
    except logic.ForumError as error:
        return _bad({"text": str(error)})
    return _topic_out(topic)


@router.post("/topics/{topic_id}/posts", response={200: FoTopicOut, 400: FoErrors})
def author_post(request, topic_id: int, body: FoAuthorPost):
    topic = get_object_or_404(Topic.objects.select_related("section"), pk=topic_id)
    name = body.name.strip()[:16]
    if not name:
        return _bad({"name": "Нужна подпись персонажа."})
    parent = Post.objects.filter(pk=body.parent, topic=topic).first() if body.parent else None
    try:
        logic.author_post(topic, name, body.text, _author_kind(body.kind), parent=parent)
    except logic.ForumError as error:
        return _bad({"text": str(error)})
    return _topic_out(topic)


@router.post("/posts/{post_id}/hide", response=FoTopicOut)
def hide(request, post_id: int, body: FoHide):
    post = get_object_or_404(Post.objects.select_related("topic__section"), pk=post_id)
    logic.hide_post(post, body.reason.strip())
    return _topic_out(Topic.objects.select_related("section").get(pk=post.topic_id))


@router.post("/posts/{post_id}/restore", response=FoTopicOut)
def restore(request, post_id: int):
    post = get_object_or_404(Post.objects.select_related("topic__section"), pk=post_id)
    logic.restore_post(post)
    return _topic_out(Topic.objects.select_related("section").get(pk=post.topic_id))
