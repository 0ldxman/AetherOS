"""Реплики персонажа: ответ во входящее или своё слово в канале (почта, форум, эфир), сразу или по игровому времени, с действиями мира.

Отложенные уходят сами: tick() зовёт промежуточный слой мира (world/middleware.py), не чаще раза в TICK секунд."""
import logging
import threading
import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from characters import inbox
from characters.models import Inbound, Reply

log = logging.getLogger("characters")
TICK = 10
_lock = threading.Lock()
_last = {"at": 0.0}


class OutboxError(ValueError):
    pass


def send_at(delay_minutes):
    """Реальный момент, когда пройдёт delay_minutes игровых минут (игровое время может идти быстрее или стоять)."""
    from machines.world import chrono

    if not delay_minutes:
        return timezone.now()
    delta = timedelta(minutes=int(delay_minutes))
    if chrono.rate_now() <= 0:                               # игровое время стоит: задержка считается по реальным минутам
        return timezone.now() + delta
    found = chrono.to_real(chrono.game_now() + delta)
    return found if found is not None else timezone.now() + delta


def _check(actions):
    from world import state

    problems = state.check_actions(actions)
    if problems:
        raise OutboxError("; ".join(problems))


@transaction.atomic
def answer(inbound, author, text, *, subject="", delay_minutes=0, actions=(), station=None):
    """Ответ во входящее: в тот же канал, тому же игроку. Входящее становится отвеченным."""
    text = (text or "").strip()
    if not text:
        raise OutboxError("пустая реплика")
    actions = list(actions or [])
    _check(actions)
    ref = {}
    if inbound.channel == Inbound.Channel.MAIL:
        persona = inbound.ref.get("persona") or inbound.character.personas.values_list("address", flat=True).first()
        if not persona:
            raise OutboxError("у персонажа нет почтового адреса")
        base = inbound.subject or ""
        subject = (subject or "").strip() or (base if base.lower().startswith("re:") else f"Re: {base}" if base else "Re:")
        ref = {"to": inbound.sender, "from": persona}
    elif inbound.channel == Inbound.Channel.FORUM:
        ref = {"topic": inbound.ref.get("topic"), "post": inbound.ref.get("post")}
    else:
        chosen = station or inbound.character.stations.order_by("pk").first()
        if chosen is None:
            raise OutboxError("у персонажа нет позывного в эфире")
        ref = {"freq": inbound.ref.get("freq"), "station": chosen.pk}
    reply = Reply.objects.create(character=inbound.character, inbound=inbound, channel=inbound.channel, author=author, user=inbound.user,
                                 subject=subject[:255], text=text, ref=ref, actions=actions, send_at=send_at(delay_minutes))
    inbox.set_status(inbound, Inbound.Status.ANSWERED, author)
    if reply.send_at <= timezone.now():
        deliver(reply)
    return reply


AUDIENCES = ("player", "group", "all")


@transaction.atomic
def say(character, author, channel, text, *, subject="", audience="player", user=None, account=None, condition=None,
        section=None, title="", freq="", station=None, delay_minutes=0, actions=()):
    """Персонаж пишет первым, без входящего.

    Почта: одному игроку в выбранную учётку (account) или многим (group: по условию, all: всем) — тогда письмо ленивое, как письмо мира,
    и приходит при следующем открытии почты. Форум: новая тема в разделе. Эфир: передача на частоте от позывного."""
    text = (text or "").strip()
    if not text:
        raise OutboxError("пустая реплика")
    actions = list(actions or [])
    _check(actions)
    ref, target = {}, None
    if channel == Inbound.Channel.MAIL:
        sender = character.personas.values_list("address", flat=True).first()
        if not sender:
            raise OutboxError("у персонажа нет почтового адреса")
        if not (subject or "").strip():
            raise OutboxError("у письма нет темы")
        if audience not in AUDIENCES:
            raise OutboxError("кому: player, group или all")
        if audience == "player":
            if account is None or not account.mail:
                raise OutboxError("выберите учётку игрока")
            ref, target = {"to": account.mail, "from": sender}, account.user or user
        else:
            if audience == "group" and not condition:
                raise OutboxError("для группы нужно условие")
            ref = {"from": sender, "audience": audience, "condition": condition if audience == "group" else None}
    elif channel == Inbound.Channel.FORUM:
        if section is None:
            raise OutboxError("выберите раздел форума")
        if not (title or "").strip():
            raise OutboxError("у темы нет заголовка")
        ref = {"section": section.pk, "title": title.strip()[:160]}
        subject = ref["title"]
    elif channel == Inbound.Channel.AIR:
        chosen = station or character.stations.order_by("pk").first()
        if chosen is None or chosen.character_id != character.pk:
            raise OutboxError("у персонажа нет позывного в эфире")
        from air import radio

        try:
            ref = {"freq": f"{radio.parse_freq(freq or radio.CALLING):.3f}", "station": chosen.pk}
        except Exception as error:                     # noqa: BLE001 — разбор частоты бросает свою ошибку с текстом
            raise OutboxError(str(error)) from None
    else:
        raise OutboxError("канал: mail, forum или air")
    reply = Reply.objects.create(character=character, channel=channel, author=author, user=target, subject=(subject or "")[:255], text=text,
                                 ref=ref, actions=actions, send_at=send_at(delay_minutes))
    if reply.send_at <= timezone.now():
        deliver(reply)
    return reply


def deliver(reply):
    """Отправить реплику в канал и выполнить её действия мира. Ошибка канала: статус failed с причиной."""
    try:
        if reply.channel == Inbound.Channel.MAIL:
            _mail_many(reply) if reply.ref.get("audience") in ("group", "all") else _mail(reply)
        elif reply.channel == Inbound.Channel.FORUM:
            _new_topic(reply) if reply.ref.get("section") else _forum(reply)
        else:
            _air(reply)
    except Exception as error:                        # noqa: BLE001 — реплика не должна ронять запрос автора, причина остаётся в журнале
        log.exception("reply %s failed", reply.pk)
        Reply.objects.filter(pk=reply.pk).update(status=Reply.Status.FAILED, error=str(error)[:255])
        reply.status, reply.error = Reply.Status.FAILED, str(error)[:255]
        return reply
    from world import state

    for action in reply.actions or []:
        state.run_action(action, f"персонаж {reply.character.code}", user=reply.user)
    now = timezone.now()
    Reply.objects.filter(pk=reply.pk).update(status=Reply.Status.SENT, sent_at=now, error="")
    reply.status, reply.sent_at = Reply.Status.SENT, now
    return reply


def _mail(reply):
    from filesystem.models import Item
    from machines.models import MachineProfile
    from mail import letters
    from mail.boxes import Box
    from mail.delivery import LETTER_FORMAT

    to = reply.ref.get("to", "")
    profile = MachineProfile.objects.filter(mail__iexact=to).select_related("machine").first()
    if profile is None:
        raise OutboxError(f"нет ящика {to}")
    body = letters.compose([("From", reply.ref.get("from", "")), ("To", to), ("Subject", reply.subject or "(no subject)")], reply.text + "\n")
    slug = f"live-{reply.character.code.lower()}-{reply.pk}"
    item = Item.objects.create(slug=slug, name=f"{slug}.msg", format=LETTER_FORMAT, body=body)
    Box.of_profile(profile, user=reply.user).deliver(item)


def _mail_many(reply):
    """Письмо многим: ленивое, приходит каждому при открытии почты (с условием — тем, чьи ключи подходят)."""
    from filesystem.models import Item
    from mail import letters
    from mail.delivery import LETTER_FORMAT
    from world import letters as world_letters

    body = letters.compose([("From", reply.ref.get("from", "")), ("To", "{to}"), ("Subject", reply.subject or "(no subject)")], reply.text + "\n")
    slug = f"live-{reply.character.code.lower()}-{reply.pk}"
    item = Item.objects.create(slug=slug, name=f"{slug}.msg", format=LETTER_FORMAT, body=body)
    world_letters.send_all(item, source=f"персонаж {reply.character.code}", condition=reply.ref.get("condition"))


def _new_topic(reply):
    from forum import logic
    from forum.models import Section

    section = Section.objects.filter(pk=reply.ref.get("section"), archived=False).first()
    if section is None:
        raise OutboxError("раздела больше нет")
    topic = logic.author_topic(section, "", reply.ref.get("title") or reply.subject, reply.text, character=reply.character)
    reply.ref = {**reply.ref, "topic": topic.pk}
    Reply.objects.filter(pk=reply.pk).update(ref=reply.ref)


def _forum(reply):
    from forum import logic
    from forum.models import Post, Topic

    topic = Topic.objects.filter(pk=reply.ref.get("topic"), hidden_at__isnull=True).first()
    if topic is None:
        raise OutboxError("темы больше нет")
    parent = Post.objects.filter(pk=reply.ref.get("post"), topic=topic, hidden_at__isnull=True).first()
    logic.author_post(topic, "", reply.text, parent=parent, character=reply.character)


def _air(reply):
    from air import radio
    from air.models import Station

    station = Station.objects.filter(pk=reply.ref.get("station")).first()
    if station is None:
        raise OutboxError("позывного больше нет")
    radio.station_transmit(station, reply.ref.get("freq") or radio.CALLING, reply.text)


def cancel(reply):
    if reply.status != Reply.Status.PENDING:
        raise OutboxError("реплика уже ушла")
    Reply.objects.filter(pk=reply.pk).update(status=Reply.Status.CANCELLED)
    reply.status = Reply.Status.CANCELLED
    return reply


def tick(force=False):
    """Отправить отложенные реплики, срок которых подошёл. Возвращает число отправленных."""
    if not force:
        with _lock:
            if time.monotonic() - _last["at"] < TICK:
                return 0
            _last["at"] = time.monotonic()
    done = 0
    for reply in Reply.objects.filter(status=Reply.Status.PENDING, send_at__lte=timezone.now()).select_related("character", "user"):
        with transaction.atomic():
            if Reply.objects.select_for_update().filter(pk=reply.pk, status=Reply.Status.PENDING).exists():
                deliver(reply)
                done += 1
    return done


def history(character, user, limit=60):
    """Переписка игрока с персонажем во всех каналах, по времени: входящие и реплики."""
    rows = [{"kind": "in", "channel": row.channel, "subject": row.subject, "text": row.text, "at": row.created_at, "author": "", "status": row.status}
            for row in Inbound.objects.filter(character=character, user=user).order_by("-created_at")[:limit]]
    rows += [{"kind": "out", "channel": row.channel, "subject": row.subject, "text": row.text, "at": row.sent_at or row.send_at,
              "author": row.author.get_username() if row.author_id else "", "status": row.status}
             for row in Reply.objects.filter(character=character, user=user).select_related("author").order_by("-created_at")[:limit]]
    return sorted(rows, key=lambda row: row["at"])[-limit:]
