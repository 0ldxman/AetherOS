"""Правила форума: кто что видит и пишет, создание тем и ответов, модерация. Без HTTP: вид (forum/views.py) и Студия (studio/api/forum.py) зовут отсюда."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from forum.models import Kind, Post, Section, Space, Topic
from secure.access import satisfied

TITLE_MAX = 160
TEXT_MAX = 4000
RATE_COUNT, RATE_SECONDS = 6, 60            # не больше шести сообщений в минуту от одного игрока
MAX_DEPTH = 6                               # глубже ответ цепляется к предку на этом уровне
MAX_SECTION_DEPTH = 2                       # игрок создаёт разделы только на первых двух уровнях дерева
PLAYER_SECTIONS = 3                         # сколько живых разделов в пространстве может быть у одного игрока


class ForumError(Exception):
    """Понятное игроку сообщение, почему нельзя."""


# ---- что видно ----

def _chain(section):
    """Раздел и его предки, от корня к разделу."""
    found = []
    while section is not None:
        found.append(section)
        section = section.parent
    return found[::-1]


def can_read(node, keys):
    """node: пространство или раздел. Читать можно, если выполнены условия пространства и всех разделов вдоль пути."""
    if isinstance(node, Space):
        return satisfied(node.read_if, keys)
    return satisfied(node.space.read_if, keys) and all(satisfied(item.read_if, keys) for item in _chain(node))


def write_mode(section):
    """Кто пишет в разделе: «players» или «authors», берётся от ближайшего раздела, где сказано, иначе от пространства."""
    for item in reversed(_chain(section)):
        if item.write != "inherit":
            return item.write
    return section.space.write


def can_write(section, user, keys):
    """Игрок пишет, если читает раздел, режим пускает игроков и выполнены все условия записи вдоль пути."""
    if user is None or not user.is_authenticated or not can_read(section, keys) or section.archived:
        return False
    if write_mode(section) != "players":
        return False
    return satisfied(section.space.write_if, keys) and all(satisfied(item.write_if, keys) for item in _chain(section))


def spaces_for(machine, keys):
    """Пространства, привязанные к машине и открытые игроку."""
    if machine is None:
        return []
    return [space for space in Space.objects.filter(machines=machine).distinct() if can_read(space, keys)]


def sections_of(space, keys):
    """Дерево разделов пространства, видимых игроку: [{section, children: [...]}]."""
    rows = list(Section.objects.filter(space=space, archived=False).select_related("space"))
    by_parent = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)
    by_id = {row.pk: row for row in rows}
    for row in rows:                                   # родители уже загружены: чтобы цепочка не ходила в базу
        row.parent = by_id.get(row.parent_id)

    def build(parent_id):
        return [{"section": row, "children": build(row.pk)} for row in by_parent.get(parent_id, []) if can_read(row, keys)]

    return build(None)


def topics_in(section):
    """Видимые темы раздела: закреплённые, затем по свежести; с числом ответов и временем последнего сообщения."""
    return (Topic.objects.filter(section=section, hidden_at__isnull=True).select_related("character")
            .annotate(replies=Count("posts", filter=Q(posts__root=False, posts__hidden_at__isnull=True))))


def posts_of(topic):
    """Сообщения темы в порядке времени; скрытое остаётся пустым местом, чтобы не рвать ветки."""
    return list(Post.objects.filter(topic=topic).select_related("character").prefetch_related("attachments").order_by("created_at", "id"))


# ---- подписи ----

def author_name(user):
    from air import radio

    return radio.callsign_of(user).name


def _clean(text, limit, what):
    text = (text or "").strip()
    if not text:
        raise ForumError(f"{what}: пусто")
    if len(text) > limit:
        raise ForumError(f"{what}: не больше {limit} знаков")
    return text


def _rate(user):
    since = timezone.now() - timedelta(seconds=RATE_SECONDS)
    if Post.objects.filter(author=user, kind=Kind.PLAYER, created_at__gte=since).count() >= RATE_COUNT:
        raise ForumError("слишком часто: подождите минуту")


# ---- записи игрока ----

@transaction.atomic
def start_topic(section, user, title, text, keys):
    if not can_write(section, user, keys):
        raise ForumError("в этот раздел писать нельзя")
    title, text = _clean(title, TITLE_MAX, "заголовок"), _clean(text, TEXT_MAX, "текст")
    _rate(user)
    return _create_topic(section, user, title, text, Kind.PLAYER, author_name(user))


@transaction.atomic
def reply(topic, user, text, keys, parent=None):
    if topic.hidden_at is not None or not can_write(topic.section, user, keys):
        raise ForumError("отвечать нельзя")
    if topic.locked:
        raise ForumError("тема закрыта")
    text = _clean(text, TEXT_MAX, "текст")
    _rate(user)
    return _add_post(topic, user, text, Kind.PLAYER, author_name(user), parent)


# ---- записи автора (Студия: персонаж или система) ----

@transaction.atomic
def author_topic(section, name, title, text, kind=Kind.CHARACTER, character=None):
    """Тема от персонажа (подпись берётся у него) или от системы (подпись как есть)."""
    if character is not None:
        name, kind = character.signature, Kind.CHARACTER
    return _create_topic(section, None, _clean(title, TITLE_MAX, "заголовок"), _clean(text, TEXT_MAX, "текст"), kind, name[:16], character)


@transaction.atomic
def author_post(topic, name, text, kind=Kind.CHARACTER, parent=None, character=None):
    if character is not None:
        name, kind = character.signature, Kind.CHARACTER
    return _add_post(topic, None, _clean(text, TEXT_MAX, "текст"), kind, name[:16], parent, character)


def _create_topic(section, user, title, text, kind, name, character=None):
    topic = Topic.objects.create(section=section, title=title, author=user, name=name, kind=kind, character=character)
    Post.objects.create(topic=topic, root=True, author=user, name=name, kind=kind, text=text, created_at=topic.created_at, character=character)
    return topic


def _add_post(topic, user, text, kind, name, parent, character=None):
    first = topic.posts.filter(root=True).first()
    if parent is not None and parent.topic_id != topic.pk:
        raise ForumError("такого сообщения в теме нет")
    parent = parent or first
    if parent is not None and parent.hidden_at is not None:
        raise ForumError("на удалённое сообщение отвечать нельзя")
    depth = 0
    walk = parent
    while walk is not None and walk.parent_id is not None:
        depth += 1
        walk = walk.parent
    while depth >= MAX_DEPTH and parent.parent is not None:
        parent, depth = parent.parent, depth - 1
    post = Post.objects.create(topic=topic, parent=parent, author=user, name=name, kind=kind, text=text, character=character)
    Topic.objects.filter(pk=topic.pk).update(bumped_at=post.created_at)
    return post


# ---- модерация ----

def hide_post(post, reason=""):
    """Корневое сообщение скрывает всю тему."""
    now = timezone.now()
    if post.root:
        Topic.objects.filter(pk=post.topic_id).update(hidden_at=now, hidden_reason=reason[:200])
    Post.objects.filter(pk=post.pk).update(hidden_at=now, hidden_reason=reason[:200])


def restore_post(post):
    if post.root:
        Topic.objects.filter(pk=post.topic_id).update(hidden_at=None, hidden_reason="")
    Post.objects.filter(pk=post.pk).update(hidden_at=None, hidden_reason="")


def set_flags(topic, pinned=None, locked=None):
    fields = {}
    if pinned is not None:
        fields["pinned"] = pinned
    if locked is not None:
        fields["locked"] = locked
    if fields:
        Topic.objects.filter(pk=topic.pk).update(**fields)


# ---- разделы игроков ----

def create_mode(space, parent):
    """Кто создаёт разделы здесь: берётся у ближайшего раздела выше, где сказано, иначе у пространства."""
    for item in reversed(_chain(parent) if parent is not None else []):
        if item.create != "inherit":
            return item.create
    return space.create


def create_problem(space, parent, user, keys):
    """Почему игрок не может создать раздел здесь (текст) или пустая строка, если может."""
    if user is None or not user.is_authenticated:
        return "создавать разделы могут только игроки"
    if parent is not None and (parent.archived or parent.space_id != space.pk):
        return "в этот раздел добавлять нельзя"
    if not (can_read(space, keys) if parent is None else can_read(parent, keys)):
        return "раздела нет"
    if create_mode(space, parent) != "players":
        return "здесь разделы создают авторы"
    conditions = [space.create_if] + [item.create_if for item in (_chain(parent) if parent is not None else [])]
    if not all(satisfied(condition, keys) for condition in conditions):
        return "пока недоступно"
    if (len(_chain(parent)) if parent is not None else 0) + 1 > MAX_SECTION_DEPTH:
        return f"глубже {MAX_SECTION_DEPTH} уровней разделы создавать нельзя"
    if Section.objects.filter(space=space, created_by=user, archived=False).count() >= PLAYER_SECTIONS:
        return f"не больше {PLAYER_SECTIONS} своих разделов: архивируйте лишний"
    return ""


def can_create(space, parent, user, keys):
    return not create_problem(space, parent, user, keys)


@transaction.atomic
def create_section(space, parent, user, title, about, keys):
    reason = create_problem(space, parent, user, keys)
    if reason:
        raise ForumError(reason)
    title = _clean(title, 120, "название")
    about = (about or "").strip()[:240]
    if Section.objects.filter(space=space, parent=parent, archived=False, title__iexact=title).exists():
        raise ForumError("раздел с таким названием уже есть")
    return Section.objects.create(space=space, parent=parent, title=title, about=about, created_by=user)


# ---- модерация создателем раздела ----

def moderates(section, user):
    """Создатель раздела (или любого раздела выше) модерирует его."""
    return user is not None and user.is_authenticated and any(item.created_by_id == user.pk for item in _chain(section))


def _need(section, user):
    if not moderates(section, user):
        raise ForumError("нет прав")


def mod_hide(post, user, reason=""):
    _need(post.topic.section, user)
    hide_post(post, reason)


def mod_restore(post, user):
    _need(post.topic.section, user)
    restore_post(post)


def mod_flags(topic, user, pinned=None, locked=None):
    _need(topic.section, user)
    set_flags(topic, pinned=pinned, locked=locked)


def mod_archive(section, user):
    _need(section, user)
    Section.objects.filter(pk=section.pk).update(archived=True)


# ---- полезные ответы ----

def can_mark_useful(topic, user):
    """Отмечать полезное может автор темы (игрок, открывший её)."""
    return user is not None and user.is_authenticated and topic.author_id == user.pk


def mark_useful(post, user, on=True):
    if not can_mark_useful(post.topic, user):
        raise ForumError("отмечать может только автор темы")
    if post.root or post.author_id == user.pk:
        raise ForumError("свои сообщения отмечать нельзя")
    if post.hidden_at is not None:
        raise ForumError("сообщение удалено")
    Post.objects.filter(pk=post.pk).update(useful=bool(on))
