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
    return (Topic.objects.filter(section=section, hidden_at__isnull=True)
            .annotate(replies=Count("posts", filter=Q(posts__root=False, posts__hidden_at__isnull=True))))


def posts_of(topic):
    """Сообщения темы в порядке времени; скрытое остаётся пустым местом, чтобы не рвать ветки."""
    return list(Post.objects.filter(topic=topic).order_by("created_at", "id"))


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
def author_topic(section, name, title, text, kind=Kind.CHARACTER):
    return _create_topic(section, None, _clean(title, TITLE_MAX, "заголовок"), _clean(text, TEXT_MAX, "текст"), kind, name)


@transaction.atomic
def author_post(topic, name, text, kind=Kind.CHARACTER, parent=None):
    return _add_post(topic, None, _clean(text, TEXT_MAX, "текст"), kind, name, parent)


def _create_topic(section, user, title, text, kind, name):
    topic = Topic.objects.create(section=section, title=title, author=user, name=name, kind=kind)
    Post.objects.create(topic=topic, root=True, author=user, name=name, kind=kind, text=text, created_at=topic.created_at)
    return topic


def _add_post(topic, user, text, kind, name, parent):
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
    post = Post.objects.create(topic=topic, parent=parent, author=user, name=name, kind=kind, text=text)
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
