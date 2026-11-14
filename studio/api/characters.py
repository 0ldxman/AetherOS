"""Персонажи в Студии: карточка (кто, как говорит, что знает), код и цвет, кто ведёт, каналы (адреса почты и позывные эфира). Логика в characters/logic.py."""
import datetime as dt
import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from air.models import Station
from air import radio
from air.models import Callsign
from characters import inbox, logic, outbox
from characters.models import Character, Inbound, Reply
from mail.models import Persona

router = Router(tags=["characters"])

_CODE = re.compile(r"^[A-Z0-9]{3}$")
_CALLSIGN = re.compile(r"^[A-Z][A-Z0-9-]{1,15}$")


class ChErrors(Schema):
    fields: dict[str, str]


class ChRow(Schema):
    id: int
    code: str
    name: str
    callsign: str
    color: int
    status: str
    owner: str
    mail: list[str]
    air: list[str]


class ChOut(ChRow):
    about: str
    voice: str
    knows: str
    note: str
    owner_id: int | None
    personas: list[int]
    stations: list[int]
    inbox: dict[str, int]        # новых входящих по каналам: mail, forum, air


class ChIn(Schema):
    name: str
    code: str = ""
    callsign: str = ""
    color: int = 0
    status: str = "active"
    about: str = ""
    voice: str = ""
    knows: str = ""
    note: str = ""
    owner_id: int | None = None
    personas: list[int] = []
    stations: list[int] = []


class ChChannel(Schema):
    id: int
    label: str
    character: int | None


class ChAuthor(Schema):
    id: int
    username: str


class ChOptions(Schema):
    personas: list[ChChannel]
    stations: list[ChChannel]
    authors: list[ChAuthor]


def _row(found):
    found_channels = logic.channels(found)
    return dict(id=found.pk, code=found.code, name=found.name, callsign=found.callsign, color=found.color, status=found.status,
                owner=found.owner.get_username() if found.owner_id else "", mail=found_channels["mail"], air=found_channels["air"])


def _out(found):
    return ChOut(**_row(found), about=found.about, voice=found.voice, knows=found.knows, note=found.note, owner_id=found.owner_id,
                 personas=list(found.personas.values_list("pk", flat=True)), stations=list(found.stations.values_list("pk", flat=True)),
                 inbox=inbox.counts(found))


@transaction.atomic
def _apply(found, body):
    errors = {}
    name = body.name.strip()
    if not name:
        errors["name"] = "Нужно имя."
    code = body.code.strip().upper() or logic.code_for(name)
    if not _CODE.match(code):
        errors["code"] = "Код: три знака, латинские буквы и цифры."
    elif Character.objects.filter(code=code).exclude(pk=found.pk).exists():
        errors["code"] = "Такой код уже у другого персонажа."
    callsign = body.callsign.strip().upper()
    if callsign and not _CALLSIGN.match(callsign):
        errors["callsign"] = "Позывной: 2–16 знаков, латиница, цифры и дефис, с буквы."
    elif callsign and Character.objects.filter(callsign=callsign).exclude(pk=found.pk).exists():
        errors["callsign"] = "Такой позывной уже у другого персонажа."
    if body.status not in Character.Status.values:
        errors["status"] = "Неизвестный статус."
    owner = None
    if body.owner_id is not None:
        owner = get_user_model().objects.filter(pk=body.owner_id, is_staff=True).first()
        if owner is None:
            errors["owner_id"] = "Вести персонажа может только автор."
    if errors:
        return errors
    found.name, found.code, found.callsign, found.color = name[:120], code, callsign, body.color % logic.COLORS
    found.status, found.about, found.voice, found.knows, found.note, found.owner = body.status, body.about, body.voice, body.knows, body.note, owner
    found.save()
    # каналы: отмеченные переходят к этому персонажу, снятые отвязываются
    Persona.objects.filter(character=found).exclude(pk__in=body.personas).update(character=None)
    Persona.objects.filter(pk__in=body.personas).update(character=found)
    Station.objects.filter(character=found).exclude(pk__in=body.stations).update(character=None)
    Station.objects.filter(pk__in=body.stations).update(character=found)
    return {}


@router.get("", response=list[ChRow])
def index(request):
    return [ChRow(**_row(found)) for found in Character.objects.select_related("owner").prefetch_related("personas", "stations")]


@router.get("/options", response=ChOptions)
def options(request):
    return ChOptions(
        personas=[ChChannel(id=p.pk, label=p.address, character=p.character_id) for p in Persona.objects.order_by("address")],
        stations=[ChChannel(id=s.pk, label=s.name, character=s.character_id) for s in Station.objects.order_by("name")],
        authors=[ChAuthor(id=u.pk, username=u.get_username()) for u in get_user_model().objects.filter(is_staff=True).order_by("username")],
    )


@router.post("", response={200: ChOut, 400: ChErrors})
def create(request, body: ChIn):
    found = Character(color=logic.color_for(body.callsign or body.name))
    errors = _apply(found, body)
    if errors:
        return 400, {"fields": errors}
    return _out(found)


@router.get("/{character_id}", response=ChOut)
def detail(request, character_id: int):
    return _out(get_object_or_404(Character, pk=character_id))


@router.put("/{character_id}", response={200: ChOut, 400: ChErrors})
def update(request, character_id: int, body: ChIn):
    found = get_object_or_404(Character, pk=character_id)
    errors = _apply(found, body)
    if errors:
        return 400, {"fields": errors}
    return _out(found)


@router.delete("/{character_id}", response={204: None})
def delete(request, character_id: int):
    get_object_or_404(Character, pk=character_id).delete()
    return 204, None


# ---- позывные эфира заводятся здесь же: станция всегда чья-то ----

class ChStationIn(Schema):
    name: str
    kind: str = "character"         # character: персонаж говорит сам; station: автоматическая станция, маяк


@router.post("/{character_id}/stations", response={200: ChOut, 400: ChErrors})
def add_station(request, character_id: int, body: ChStationIn):
    found = get_object_or_404(Character, pk=character_id)
    name = body.name.strip().upper()
    if not radio._NAME.match(name):
        return 400, {"fields": {"station": "Позывной: 2–12 латинских букв, цифр или дефисов, начинается с буквы."}}
    if Station.objects.filter(name=name).exists() or Callsign.objects.filter(name=name).exists():
        return 400, {"fields": {"station": f"Позывной {name} уже занят."}}
    kind = body.kind if body.kind in Station.Kind.values else Station.Kind.CHARACTER
    Station.objects.create(name=name, label=found.name[:120], kind=kind, character=found)
    if not found.callsign:
        found.callsign = name
        found.save(update_fields=["callsign"])
    return _out(found)


# ---- входящие ----

class ChInbound(Schema):
    id: int
    channel: str
    sender: str
    player: str
    subject: str
    text: str
    status: str
    taken_by: str
    created_at: dt.datetime
    link: str                       # куда смотреть в Студии: тема форума, частота эфира, путь письма


class ChStatusIn(Schema):
    status: str


def _link(row):
    if row.channel == Inbound.Channel.FORUM:
        from forum.models import Topic

        topic = Topic.objects.filter(pk=row.ref.get("topic")).select_related("section__space").first()
        return f"#/forum/{topic.section.space.slug}/topics" if topic else ""
    if row.channel == Inbound.Channel.AIR:
        return f"частота {row.ref.get('freq', '')}"
    return row.ref.get("path", "")


def _inbound(row):
    return ChInbound(id=row.pk, channel=row.channel, sender=row.sender, player=row.user.get_username() if row.user_id else "", subject=row.subject,
                     text=row.text, status=row.status, taken_by=row.taken_by.get_username() if row.taken_by_id else "", created_at=row.created_at,
                     link=_link(row))


@router.get("/{character_id}/inbox", response=list[ChInbound])
def inbox_list(request, character_id: int, channel: str = "", status: str = "open"):
    """status: open (новые и взятые), new, taken, answered, skipped, all."""
    found = get_object_or_404(Character, pk=character_id)
    rows = Inbound.objects.filter(character=found).select_related("user", "taken_by")
    if channel:
        rows = rows.filter(channel=channel)
    if status == "open":
        rows = rows.filter(status__in=(Inbound.Status.NEW, Inbound.Status.TAKEN))
    elif status != "all":
        rows = rows.filter(status=status)
    return [_inbound(row) for row in rows[:300]]


@router.post("/inbox/{inbound_id}/status", response={200: ChInbound, 400: ChErrors})
def inbox_status(request, inbound_id: int, body: ChStatusIn):
    row = get_object_or_404(Inbound.objects.select_related("user"), pk=inbound_id)
    if body.status not in Inbound.Status.values:
        return 400, {"fields": {"status": "Неизвестный статус."}}
    return _inbound(inbox.set_status(row, body.status, request.user))


# ---- реплики персонажа ----

class ChReply(Schema):
    id: int
    inbound: int | None
    channel: str
    author: str
    player: str
    subject: str
    text: str
    status: str
    error: str
    send_at: dt.datetime
    sent_at: dt.datetime | None
    actions: list[dict]
    where: str


class ChAnswerIn(Schema):
    text: str
    subject: str = ""
    delay: int = 0                    # игровые минуты
    actions: list[dict] = []
    station: int | None = None


class ChHistory(Schema):
    kind: str                         # in | out
    channel: str
    subject: str
    text: str
    at: dt.datetime
    author: str
    status: str


class ChPlayer(Schema):
    username: str
    callsign: str
    accounts: list[str]
    keys: list[str]
    online: bool


class ChContext(Schema):
    player: ChPlayer | None
    history: list[ChHistory]
    replies: list[ChReply]
    stations: list[ChChannel]


def _where(row):
    if row.channel == Inbound.Channel.MAIL:
        return f"{row.ref.get('from', '')} → {row.ref.get('to', '')}"
    if row.channel == Inbound.Channel.FORUM:
        return f"тема {row.ref.get('topic')}"
    return f"{row.ref.get('freq', '')}"


def _reply(row):
    return ChReply(id=row.pk, inbound=row.inbound_id, channel=row.channel, author=row.author.get_username() if row.author_id else "",
                   player=row.user.get_username() if row.user_id else "", subject=row.subject, text=row.text, status=row.status, error=row.error,
                   send_at=row.send_at, sent_at=row.sent_at, actions=row.actions or [], where=_where(row))


def _player(user):
    if user is None:
        return None
    from air.radio import callsign_of
    from team import players

    card = players.card(user)
    return ChPlayer(username=user.get_username(), callsign=callsign_of(user).name,
                    accounts=[f"{row['profile'].login}@{row['profile'].machine.hostname}" for row in card["accounts"]],
                    keys=sorted({row["name"] or row["slug"] for row in card["keys"]}), online=card["online"])


@router.post("/inbox/{inbound_id}/answer", response={200: ChReply, 400: ChErrors})
def answer(request, inbound_id: int, body: ChAnswerIn):
    row = get_object_or_404(Inbound.objects.select_related("character", "user"), pk=inbound_id)
    station = Station.objects.filter(pk=body.station, character=row.character).first() if body.station else None
    try:
        made = outbox.answer(row, request.user, body.text, subject=body.subject, delay_minutes=max(0, body.delay), actions=body.actions, station=station)
    except outbox.OutboxError as error:
        return 400, {"fields": {"text": str(error)}}
    return _reply(made)


@router.get("/inbox/{inbound_id}/context", response=ChContext)
def context(request, inbound_id: int):
    row = get_object_or_404(Inbound.objects.select_related("character", "user"), pk=inbound_id)
    history = [ChHistory(**item) for item in outbox.history(row.character, row.user)] if row.user_id else []
    replies = [_reply(r) for r in row.replies.select_related("author", "user")]
    stations = [ChChannel(id=s.pk, label=s.name, character=s.character_id) for s in row.character.stations.order_by("pk")]
    return ChContext(player=_player(row.user), history=history, replies=replies, stations=stations)


@router.get("/{character_id}/replies", response=list[ChReply])
def replies(request, character_id: int):
    found = get_object_or_404(Character, pk=character_id)
    return [_reply(r) for r in Reply.objects.filter(character=found).select_related("author", "user")[:300]]


@router.post("/replies/{reply_id}/cancel", response={200: ChReply, 400: ChErrors})
def cancel_reply(request, reply_id: int):
    row = get_object_or_404(Reply.objects.select_related("author", "user"), pk=reply_id)
    try:
        return _reply(outbox.cancel(row))
    except outbox.OutboxError as error:
        return 400, {"fields": {"status": str(error)}}
