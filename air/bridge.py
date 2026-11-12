"""Мост эфира с Discord: логика без библиотеки Discord (её держит air/discord_bot.py).

Эфир → Discord: новая передача на частоте с мостом встаёт в очередь (BridgeMessage), бот публикует её в канал так, как её слышит
человек без ключа: шифровку шифровкой. Песочные, скрытые и передачи под условием на ключ в канал не идут.
Discord → эфир: сообщение канала выходит в эфир от позывного игрока, чей Discord привязан ко входу (allauth). Заглушка, «только приём»,
окна полос и лимиты действуют как у игрока. Скрытие передачи в Студии удаляет её и в Discord.

Аренда: бот подключается, только если держит BridgeState (продлевает каждые BEAT секунд). Так при нескольких процессах сайта
к Discord подключается ровно один, а упавший процесс через LEASE отдаёт мост другому.
"""
import os
import socket
from datetime import timedelta

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from air.models import BridgeLink, BridgeMessage, BridgeState, Transmission

BEAT = 10
LEASE = timedelta(seconds=45)
MAX_ATTEMPTS = 5
DISCORD_LIMIT = 2000


def token():
    return os.environ.get("DISCORD_BOT_TOKEN", "").strip()


# ---------- эфир → Discord ----------

def _eligible(sent):
    return not sent.sandbox and sent.hidden_at is None and not sent.condition and sent.via != "discord"


@receiver(post_save, sender=Transmission)
def _queue(sender, instance, created, **kwargs):
    if not created or not _eligible(instance):
        return
    link = BridgeLink.objects.filter(freq=instance.freq, active=True).first()
    if link is not None:
        BridgeMessage.objects.create(transmission=instance, link=link)


def render(sent):
    """Текст для канала: частота, позывной, как звучит в эфире."""
    return f"`{sent.freq:.3f}` **{sent.callsign}**: {sent.on_air or sent.text}"[:DISCORD_LIMIT]


def outbox(limit=20):
    """Что отправить: [(id, канал, текст)]."""
    rows = (BridgeMessage.objects.filter(state=BridgeMessage.State.QUEUED, inbound=False, link__active=True)
            .select_related("transmission", "link").order_by("pk")[:limit])
    return [(row.pk, row.link.channel_id, render(row.transmission)) for row in rows]


def sent(message_id, discord_id):
    BridgeMessage.objects.filter(pk=message_id).update(state=BridgeMessage.State.SENT, discord_id=str(discord_id), error="")


def failed(message_id, error):
    row = BridgeMessage.objects.filter(pk=message_id).first()
    if row is None:
        return
    row.attempts += 1
    row.error = str(error)[:200]
    row.state = BridgeMessage.State.FAILED if row.attempts >= MAX_ATTEMPTS else row.state
    row.save(update_fields=["attempts", "error", "state"])


def to_delete(limit=20):
    """Что удалить в Discord: [(id, канал, id сообщения Discord)]."""
    rows = BridgeMessage.objects.filter(state=BridgeMessage.State.DELETE).select_related("link").order_by("pk")[:limit]
    return [(row.pk, row.link.channel_id, row.discord_id) for row in rows]


def deleted(message_id):
    BridgeMessage.objects.filter(pk=message_id).update(state=BridgeMessage.State.DELETED)


def on_hide(transmission):
    """Передачу скрыли: ушедшее в Discord удалить, неотправленное не отправлять."""
    rows = BridgeMessage.objects.filter(transmission=transmission)
    rows.filter(state=BridgeMessage.State.QUEUED).update(state=BridgeMessage.State.DELETED)
    rows.filter(state=BridgeMessage.State.SENT).exclude(discord_id="").update(state=BridgeMessage.State.DELETE)


def on_unhide(transmission):
    """Передачу вернули: в канал она уходит заново (из Discord её уже удалили)."""
    rows = BridgeMessage.objects.filter(transmission=transmission, inbound=False, state__in=(BridgeMessage.State.DELETED, BridgeMessage.State.DELETE))
    if rows.exists():
        rows.update(state=BridgeMessage.State.QUEUED, discord_id="", attempts=0)
    elif _eligible(transmission):
        _queue(Transmission, transmission, True)


# ---------- Discord → эфир ----------

def player_of(discord_user_id):
    from allauth.socialaccount.models import SocialAccount

    account = SocialAccount.objects.filter(provider="discord", uid=str(discord_user_id)).select_related("user").first()
    return account.user if account else None


def inbound(channel_id, discord_user_id, text, message_id):
    """Сообщение из канала Discord: выйти в эфир от позывного игрока. Возвращает (передача или None, причина отказа)."""
    from air import radio

    link = BridgeLink.objects.filter(channel_id=str(channel_id), active=True).first()
    if link is None:
        return None, "no bridge"
    user = player_of(discord_user_id)
    if user is None:
        return None, "sign in to the game with Discord to transmit"
    try:
        made = radio.transmit(user, link.freq, text, via="discord")
    except radio.AirError as error:
        return None, str(error)
    BridgeMessage.objects.create(transmission=made, link=link, inbound=True, discord_id=str(message_id), state=BridgeMessage.State.SENT)
    return made, ""


# ---------- аренда ----------

def holder_name():
    return f"{socket.gethostname()}:{os.getpid()}"


def lease(holder, bot_name="", error=""):
    """Взять или продлить мост. True — этот процесс держит бота."""
    now = timezone.now()
    with transaction.atomic():
        state, _ = BridgeState.objects.select_for_update().get_or_create(pk=1)
        if state.holder and state.holder != holder and state.seen_at and now - state.seen_at < LEASE:
            return False
        state.holder, state.seen_at = holder, now
        if bot_name:
            state.bot_name = bot_name
        state.error = error[:300]
        state.save()
    return True


def release(holder):
    BridgeState.objects.filter(pk=1, holder=holder).update(holder="", seen_at=None)


def status():
    """Для Студии: есть ли токен, на связи ли бот, когда виден был последний раз, ошибка."""
    state = BridgeState.objects.filter(pk=1).first()
    online = bool(state and state.holder and state.seen_at and timezone.now() - state.seen_at < LEASE)
    return {"token": bool(token()), "online": online, "bot": state.bot_name if state else "", "seen_at": state.seen_at if state else None,
            "error": state.error if state else ""}
