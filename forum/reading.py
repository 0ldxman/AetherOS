"""Что игрок уже читал: новое с прошлого визита в теме, сводки тем и разделов для списков."""
import re

from django.db.models import Max
from django.utils import timezone

from forum.models import Post, Reader, Visit

EXCERPT = 160


def plain(text):
    """Текст без разметки (# - > ** * `), одной строкой: для превью темы."""
    text = re.sub(r"^\s*(#{1,3}\s+|[-*]\s+|>\s?)", "", text or "", flags=re.MULTILINE)
    text = " ".join(re.sub(r"(\*\*|\*|`)", "", text).split())
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1].rstrip() + "…"


def since(user):
    """С какого момента для игрока бывает «новое» (первое открытие форума); None у гостя."""
    if user is None or not user.is_authenticated:
        return None
    return Reader.objects.get_or_create(user=user)[0].since


def _thresholds(user, topic_ids):
    start = since(user)
    if start is None:
        return {}
    seen = dict(Visit.objects.filter(user=user, topic_id__in=topic_ids).values_list("topic_id", "seen_at"))
    # кто ответил в теме, тот видел всё, что было до его ответа
    wrote = dict(Post.objects.filter(author=user, topic_id__in=topic_ids).values("topic_id").annotate(last=Max("created_at")).values_list("topic_id", "last"))
    return {pk: max(seen.get(pk, start), wrote.get(pk, start), start) for pk in topic_ids}


def summaries(topics, user):
    """{id темы: {excerpt, replies, last_name, last_at, new, unseen}} одним запросом по сообщениям."""
    ids = [topic.pk for topic in topics]
    marks = _thresholds(user, ids)
    out = {pk: {"excerpt": "", "replies": 0, "last_name": "", "last_at": None, "new": 0, "unseen": False} for pk in ids}
    rows = Post.objects.filter(topic_id__in=ids, hidden_at__isnull=True).values_list("topic_id", "root", "name", "created_at", "author_id", "text")
    for topic_id, root, name, created, author_id, text in rows.order_by("created_at", "id"):
        found = out[topic_id]
        if root:
            found["excerpt"] = plain(text)
        else:
            found["replies"] += 1
        found["last_name"], found["last_at"] = name, created
        mark = marks.get(topic_id)
        if mark is not None and created > mark and (user is None or author_id != user.pk):
            if root:
                found["unseen"] = True
            else:
                found["new"] += 1
    return out


def new_posts(topic, user):
    """Номера сообщений темы, появившихся после прошлого визита игрока (не его собственных)."""
    mark = _thresholds(user, [topic.pk]).get(topic.pk)
    if mark is None:
        return set()
    return set(Post.objects.filter(topic=topic, created_at__gt=mark).exclude(author=user).values_list("pk", flat=True))


def mark_seen(topic, user):
    if user is None or not user.is_authenticated:
        return
    since(user)
    Visit.objects.update_or_create(user=user, topic=topic, defaults={"seen_at": timezone.now()})
