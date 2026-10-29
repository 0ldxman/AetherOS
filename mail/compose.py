"""Задачи на набор: разбор целевого текста, доступность, проверка и отправка.

Сервер сам сверяет текст (интерфейс только помогает): скрытые части ({{...}}) в браузер
не уходят, он знает лишь их длину.
"""
import re
from dataclasses import dataclass
from django.db import transaction
from django.utils import timezone

from machines.world import GAME_NOW
from secure.access import satisfied

from mail.delivery import deliver
from mail.models import ComposeProgress, ComposeTask, Message

HIDDEN = re.compile(r"\{\{(.+?)\}\}", re.DOTALL)


def segments(target):
    """Целевой текст по частям: ("text", строка) и ("hidden", значение)."""
    parts, last = [], 0

    for match in HIDDEN.finditer(target):
        if match.start() > last:
            parts.append(("text", target[last:match.start()]))
        parts.append(("hidden", match.group(1)))
        last = match.end()

    if last < len(target):
        parts.append(("text", target[last:]))

    return parts


def expected_text(task):
    """Весь текст, который должен набрать игрок (со значениями скрытых частей)."""
    return "".join(value for _, value in segments(normalize(task.target)))


def public_segments(task):
    """Что видит браузер: видимый текст и только длина скрытого."""
    return [
        {"text": value} if kind == "text" else {"hidden": len(value)}
        for kind, value in segments(normalize(task.target))
    ]


def normalize(text):
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def available_tasks(viewer):
    """Задачи, которые игрок может сейчас выполнить: он вошёл под профилем задачи, ключи, ещё не отправлено."""
    if viewer.user is None or viewer.profile is None:
        return []

    done = set(
        ComposeProgress.objects.filter(user=viewer.user, sent_at__isnull=False).values_list("task_id", flat=True)
    )
    tasks = ComposeTask.objects.filter(profile=viewer.profile)

    return [
        task for task in tasks
        if task.pk not in done and (task.key_condition is None or satisfied(task.key_condition, viewer.keys))
    ]


class TaskError(Exception):
    def __init__(self, message, status, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


@dataclass(frozen=True)
class SendResult:
    copy: Message          # письмо игрока в «отправленных»
    replies: int           # сколько ответов поставлено в очередь
    delay: int             # через сколько секунд они придут


def _left(task, attempts):
    return None if not task.max_attempts else max(0, task.max_attempts - attempts)


def send(user, task, text, now=None):
    """Отправить набранное. Верно: письмо в «отправленных» и ответы с задержкой. Неверно: попытка тратится.

    Ошибка выбрасывается уже после транзакции: иначе откат отменил бы и записанную неудачную попытку,
    и скрытое значение можно было бы перебирать бесконечно."""
    result = _attempt(user, task, text, now or timezone.now())

    if isinstance(result, TaskError):
        raise result

    return result


@transaction.atomic
def _attempt(user, task, text, now):
    progress, _ = ComposeProgress.objects.select_for_update().get_or_create(task=task, user=user)

    if progress.sent_at is not None:
        return TaskError("already sent", 409)

    if task.max_attempts and progress.attempts >= task.max_attempts:
        return TaskError("the message is locked: too many failed attempts", 423, attempts_left=0)

    if normalize(text) != expected_text(task):
        progress.attempts += 1
        progress.save(update_fields=["attempts"])
        return TaskError("message rejected", 422, attempts_left=_left(task, progress.attempts))

    copy = Message.objects.create(
        sender=task.profile.mail,
        recipients=task.recipients,
        subject=task.subject,
        body=normalize(text),
        sent_at=GAME_NOW,
        slug=f"sent-{task.pk}-{user.pk}",    # копия видна только тому, кому её доставили
    )
    deliver(user, copy, delay=0, now=now)

    replies = list(task.replies.all())
    for reply in replies:
        deliver(user, reply, delay=task.reply_delay, now=now)

    progress.sent_at = now
    progress.text = normalize(text)
    progress.save(update_fields=["sent_at", "text"])
    return SendResult(copy, len(replies), task.reply_delay)
