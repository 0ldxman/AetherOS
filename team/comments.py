"""Обсуждения сущностей Студии: ветки комментариев с ответами, упоминаниями @имя и отметкой «решено».

Сущность называется тем же путём API, что и в ленте (team.changes): machines/3, items/7, systems/AETHER. Поэтому обсуждать
можно всё, что правится в Студии, а вид, подпись и ссылка берутся оттуда же.
"""
import re

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from team import changes
from team.models import Comment

MENTION = re.compile(r"(?<![\w@])@([\w.+-]+)")
MAX_TEXT = 4000
INBOX_LIMIT = 20


class CommentError(Exception):
    pass


def _clean_target(target):
    target = (target or "").strip().strip("/")
    if not target or len(target) > 512:
        raise CommentError("Не указано, что обсуждается.")
    return target


def _mentioned(text):
    names = {name.rstrip(".") for name in MENTION.findall(text)}
    return list(get_user_model().objects.filter(is_staff=True, username__in=names)) if names else []


def threads(target):
    """Ветки сущности: корни с ответами, открытые сначала, внутри по времени."""
    roots = (Comment.objects.filter(target=_clean_target(target), parent__isnull=True)
             .prefetch_related("replies", "mentions", "replies__mentions"))
    return sorted(roots, key=lambda c: (c.resolved_at is not None, c.created_at))


def post(user, target, text, parent_id=None):
    text = (text or "").strip()
    if not text:
        raise CommentError("Пустое сообщение.")
    if len(text) > MAX_TEXT:
        raise CommentError(f"Слишком длинно: больше {MAX_TEXT} символов.")
    parent = None
    if parent_id is not None:
        parent = Comment.objects.filter(pk=parent_id, parent__isnull=True).first()
        if parent is None:
            raise CommentError("Ветки, на которую вы отвечаете, нет.")
        target = parent.target
    target = _clean_target(target)
    kind, label, link, _, _ = changes.describe(target)
    comment = Comment.objects.create(target=target, kind=kind, label=label[:200], link=link, parent=parent,
                                     author=user, username=user.get_username(), text=text)
    comment.mentions.set(_mentioned(text))
    if parent is not None and parent.resolved_at:
        parent.resolved_at, parent.resolved_by = None, ""                 # ответ снова открывает обсуждение
        parent.save(update_fields=["resolved_at", "resolved_by"])
    return comment


def _own(user, comment_id):
    comment = Comment.objects.filter(pk=comment_id).first()
    if comment is None:
        raise CommentError("Сообщения нет.")
    if comment.author_id != user.pk and not user.is_superuser:
        raise CommentError("Править и удалять можно только свои сообщения.")
    return comment


def edit(user, comment_id, text):
    comment = _own(user, comment_id)
    text = (text or "").strip()
    if not text:
        raise CommentError("Пустое сообщение.")
    comment.text, comment.edited_at = text[:MAX_TEXT], timezone.now()
    comment.save(update_fields=["text", "edited_at"])
    comment.mentions.set(_mentioned(text))
    return comment


def delete(user, comment_id):
    _own(user, comment_id).delete()


def resolve(user, comment_id, resolved):
    comment = Comment.objects.filter(pk=comment_id).first()
    if comment is None:
        raise CommentError("Сообщения нет.")
    root = comment.parent or comment
    root.resolved_at = timezone.now() if resolved else None
    root.resolved_by = user.get_username() if resolved else ""
    root.save(update_fields=["resolved_at", "resolved_by"])
    return root


def counts(targets):
    """Число открытых веток по сущностям (для значка на кнопке обсуждения)."""
    found = {}
    for target in Comment.objects.filter(target__in=targets, parent__isnull=True, resolved_at__isnull=True).values_list("target", flat=True):
        found[target] = found.get(target, 0) + 1
    return found


def inbox(user, limit=INBOX_LIMIT):
    """Открытые ветки, которые касаются автора: его упомянули или он в них писал. Свежие сверху."""
    touched = Comment.objects.filter(Q(mentions=user) | Q(author=user))
    root_ids = {c.parent_id or c.pk for c in touched.only("pk", "parent_id")}
    roots = (Comment.objects.filter(pk__in=root_ids, resolved_at__isnull=True)
             .prefetch_related("replies", "mentions", "replies__mentions"))
    rows = []
    for root in roots:
        messages = [root, *root.replies.all()]
        last = messages[-1]
        mentioned = any(user in m.mentions.all() for m in messages)
        waiting = last.author_id != user.pk                              # последним писал не он: есть что прочесть
        rows.append({"root": root, "last": last, "count": len(messages), "mentioned": mentioned, "waiting": waiting})
    rows.sort(key=lambda r: r["last"].created_at, reverse=True)
    return rows[:limit]


def open_total():
    return Comment.objects.filter(parent__isnull=True, resolved_at__isnull=True).count()
