"""Входящие персонажа: что игроки пишут ему вне сценариев. Ловится в почте (письмо на адрес без варианта),
на форуме (ответ на его сообщение или полный позывной в тексте) и в эфире (полный позывной в передаче).

Решение: упоминание это только полный позывной (OPERATOR-7), не код и не имя."""
import re

from django.db.models import Count
from django.utils import timezone

from characters.models import Character, Inbound


def _callsigns():
    """{ПОЗЫВНОЙ: персонаж}: позывные карточек и станций эфира, привязанных к персонажам."""
    from air.models import Station

    found = {}
    for character in Character.objects.exclude(callsign=""):
        found[character.callsign.upper()] = character
    for station in Station.objects.filter(character__isnull=False).select_related("character"):
        found.setdefault(station.name.upper(), station.character)
    return found


def mentioned(text):
    """Персонажи, чей полный позывной стоит в тексте отдельным словом (без учёта регистра)."""
    upper = (text or "").upper()
    out = []
    for sign, character in _callsigns().items():
        if re.search(r"(?<![A-Z0-9-])" + re.escape(sign) + r"(?![A-Z0-9-])", upper) and character not in out:
            out.append(character)
    return out


def capture_mail(persona, user, sender, subject, text, machine, path):
    """Письмо игрока на адрес персонажа без выбранного варианта сценария."""
    if persona is None or persona.character_id is None or user is None:
        return None
    return Inbound.objects.create(character_id=persona.character_id, channel=Inbound.Channel.MAIL, user=user, sender=sender[:255],
                                  subject=(subject or "")[:255], text=text or "", ref={"machine": machine.pk if machine else None, "path": path})


def capture_forum(post):
    """Сообщение игрока на форуме: ответ на сообщение персонажа и полные позывные в тексте (по одной записи на персонажа)."""
    if post.author_id is None:
        return []
    targets = []
    parent = post.parent
    if parent is not None and parent.character_id is not None and not parent.root:
        targets.append(parent.character)
    elif parent is not None and parent.root and parent.character_id is not None:
        targets.append(parent.character)                       # ответ в тему, которую открыл персонаж
    for character in mentioned(post.text if not post.root else f"{post.topic.title}\n{post.text}"):
        if character not in targets:
            targets.append(character)
    return [Inbound.objects.create(character=character, channel=Inbound.Channel.FORUM, user=post.author, sender=post.name,
                                   subject=post.topic.title[:255], text=post.text, ref={"topic": post.topic_id, "post": post.pk})
            for character in targets]


def capture_air(transmission):
    """Передача игрока с полным позывным персонажа."""
    if transmission.user_id is None:
        return []
    return [Inbound.objects.create(character=character, channel=Inbound.Channel.AIR, user=transmission.user, sender=transmission.callsign,
                                   text=transmission.text, ref={"transmission": transmission.pk, "freq": f"{transmission.freq:.3f}"})
            for character in mentioned(transmission.text)]


def counts(character):
    """{канал: число новых}."""
    rows = Inbound.objects.filter(character=character, status=Inbound.Status.NEW).values("channel").annotate(n=Count("id"))
    return {channel: 0 for channel in Inbound.Channel.values} | {row["channel"]: row["n"] for row in rows}


def set_status(inbound, status, by):
    """Взять (за автором), отметить отвеченным или пропущенным, вернуть в новые."""
    if status not in Inbound.Status.values:
        raise ValueError(status)
    inbound.status = status
    if status == Inbound.Status.TAKEN:
        inbound.taken_by, inbound.taken_at = by, timezone.now()
    elif status == Inbound.Status.NEW:
        inbound.taken_by, inbound.taken_at = None, None
    inbound.save(update_fields=["status", "taken_by", "taken_at"])
    return inbound
