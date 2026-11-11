"""Лента новостей игрока и прочитанность. Студия правит новости через эти же функции (studio/api/news.py)."""
from django.db import IntegrityError, transaction
from django.utils import timezone

from news.models import Post, PostRead

LIMIT = 100


def published(now=None):
    return Post.objects.filter(publish_at__isnull=False, publish_at__lte=now or timezone.now())


def read_ids(user):
    if user is None or not user.is_authenticated:
        return set()
    return set(PostRead.objects.filter(user=user).values_list("post_id", flat=True))


def feed(user):
    """Опубликованные новости, закреплённые первыми, и прочитал ли их игрок (гость: всё прочитано, отмечать нечего)."""
    seen = read_ids(user)
    guest = user is None or not user.is_authenticated
    return [(post, guest or post.pk in seen) for post in published().select_related("author")[:LIMIT]]


def mark_read(user, ids):
    if user is None or not user.is_authenticated:
        return 0
    made = 0
    for post in published().filter(pk__in=ids):
        try:
            with transaction.atomic():
                PostRead.objects.create(post=post, user=user)
                made += 1
        except IntegrityError:
            pass
    return made


def pulse(user):
    """Для стола: сколько непрочитанных и сами непрочитанные (свежие сверху), важные отмечены."""
    rows = [post for post, read in feed(user) if not read]
    return {"unread": len(rows), "items": [{"id": post.pk, "title": post.title, "important": post.important} for post in rows[:20]]}


def save(post, *, title, body, publish_at, pinned, important, author=None):
    post.title, post.body, post.publish_at, post.pinned, post.important = title.strip(), body, publish_at, pinned, important
    if post.author_id is None and author is not None:
        post.author = author
    post.save()
    return post
