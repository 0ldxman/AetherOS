"""Эфир в Студии: живая лента всех частот, модерация, позывные с настоящими игроками, станции, полосы, жалобы. Логика в air/radio.py."""
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from django.utils import timezone

from air import cipher, events, radio, schedule
from air.models import Band, BridgeLink, BridgeMessage, Broadcast, Callsign, CallsignChange, Report, Responder, Station, Transmission
from machines.access import windows
from machines.world import chrono

router = Router(tags=["air"])


class AirPlayer(Schema):
    id: int
    username: str
    discord: str


class AirRow(Schema):
    id: int
    freq: str
    callsign: str
    station: bool
    player: AirPlayer | None
    sandbox: bool
    text: str
    at: datetime
    hidden: bool
    hidden_reason: str
    key: str = ""               # ключ шифра, если передали с ключом
    on_air: str = ""            # как звучит в эфире (шифровка)
    reports: int


class AirHide(Schema):
    reason: str = ""


class AirChange(Schema):
    old: str
    new: str
    at: datetime
    by: str


class AirSign(Schema):
    player: AirPlayer
    name: str
    changed_at: datetime | None
    muted_until: datetime | None
    rx_only: bool
    history: list[AirChange]


class AirSignIn(Schema):
    name: str | None = None
    rx_only: bool | None = None
    mute_minutes: int | None = None          # 0: снять заглушку


class AirStation(Schema):
    id: int
    name: str
    label: str
    kind: str


class AirStationIn(Schema):
    name: str
    label: str = ""
    kind: str = "station"


class AirBand(Schema):
    id: int
    low: str
    high: str
    kind: str
    condition: object = None
    label: str
    window: str
    time_zone: str
    open_now: float            # 1 — проходит, 0 — тишина, между — край окна


class AirBandIn(Schema):
    low: str
    high: str
    kind: str = "reserved"
    condition: object = None
    label: str = ""
    window: str = ""
    time_zone: str = "UTC"


class AirBroadcast(Schema):
    id: int
    station: int
    freq: str
    texts: list[str]
    schedule: str
    time_zone: str
    condition: object = None
    active: bool
    note: str
    key: str
    summary: str               # расписание словами
    last_at: datetime | None   # игровое UTC
    next_at: datetime | None


class AirBroadcastIn(Schema):
    station: int
    freq: str
    texts: list[str]
    schedule: str
    time_zone: str = "UTC"
    condition: object = None
    active: bool = True
    note: str = ""
    key: str = ""


class AirResponder(Schema):
    id: int
    station: int
    freq: str
    pattern: str
    regex: bool
    condition: object = None
    cooldown: int
    reply: str
    delay: int
    actions: list[dict]
    active: bool
    note: str
    key: str
    fires: int                 # сколько раз срабатывал


class AirResponderIn(Schema):
    station: int
    freq: str
    pattern: str
    regex: bool = False
    condition: object = None
    cooldown: int = 10
    reply: str = ""
    delay: int = 5
    actions: list[dict] = []
    active: bool = True
    note: str = ""
    key: str = ""


class AirTx(Schema):
    station: int
    freq: str
    text: str
    key: str = ""


class AirReport(Schema):
    id: int
    transmission: AirRow
    reporter: AirPlayer
    reason: str
    at: datetime


def _player(user):
    if user is None:
        return None
    return AirPlayer(id=user.pk, username=user.get_username(), discord=radio._discord_name(user))


def _row(row):
    return AirRow(id=row.pk, freq=f"{row.freq:.3f}", callsign=row.callsign, station=row.station_id is not None, player=_player(row.user),
                  sandbox=row.sandbox, text=row.text, at=row.created_at, hidden=row.hidden_at is not None, hidden_reason=row.hidden_reason,
                  key=row.key, on_air=row.on_air,
                  reports=getattr(row, "report_count", 0))


def _refuse(error):
    raise ValidationError({"__all__": [str(error)]})


@router.get("/feed", response=list[AirRow])
def feed(request, freq: str = "", q: str = "", after: int = 0, limit: int = 200):
    """Передачи всех частот за последние 24 часа, свежие сверху. after: только новее этой (живая лента)."""
    found = Transmission.objects.select_related("user").prefetch_related("user__socialaccount_set").annotate(report_count=Count("reports"))
    if freq.strip():
        try:
            found = found.filter(freq=radio.parse_freq(freq))
        except radio.AirError as error:
            _refuse(error)
    if q.strip():
        text = q.strip()
        found = found.filter(Q(callsign__icontains=text) | Q(text__icontains=text) | Q(user__username__icontains=text))
    if after:
        found = found.filter(pk__gt=after)
    return [_row(row) for row in found.order_by("-created_at", "-pk")[:max(1, min(limit, 500))]]


@router.post("/transmissions/{int:tx_id}/hide", response=AirRow)
def hide(request, tx_id: int, body: AirHide):
    row = get_object_or_404(Transmission, pk=tx_id)
    radio.hide(row, request.user, body.reason)
    return _row(row)


@router.post("/transmissions/{int:tx_id}/unhide", response=AirRow)
def unhide(request, tx_id: int):
    row = get_object_or_404(Transmission, pk=tx_id)
    radio.unhide(row)
    return _row(row)


@router.post("/transmit", response=AirRow)
def transmit(request, body: AirTx):
    """Передать от станции или персонажа (без лимитов игрока, в любой полосе)."""
    try:
        return _row(radio.station_transmit(get_object_or_404(Station, pk=body.station), body.freq, body.text, key=body.key))
    except radio.AirError as error:
        _refuse(error)


def _sign(sign):
    changes = CallsignChange.objects.filter(user=sign.user).select_related("by")[:20]
    return AirSign(player=_player(sign.user), name=sign.name, changed_at=sign.changed_at, muted_until=sign.muted_until, rx_only=sign.rx_only,
                   history=[AirChange(old=c.old, new=c.new, at=c.at, by=c.by.get_username() if c.by else "") for c in changes])


@router.get("/callsigns", response=list[AirSign])
def callsigns(request, q: str = ""):
    found = Callsign.objects.select_related("user").prefetch_related("user__socialaccount_set").filter(user__sandbox_of__isnull=True)
    if q.strip():
        found = found.filter(Q(name__icontains=q.strip()) | Q(user__username__icontains=q.strip()))
    return [_sign(sign) for sign in found.order_by("name")[:300]]


@router.get("/callsigns/{int:user_id}", response=AirSign)
def callsign(request, user_id: int):
    return _sign(radio.callsign_of(get_object_or_404(get_user_model(), pk=user_id)))


@router.put("/callsigns/{int:user_id}", response=AirSign)
def change_callsign(request, user_id: int, body: AirSignIn):
    user = get_object_or_404(get_user_model(), pk=user_id)
    try:
        if body.name is not None:
            radio.rename(user, body.name, by=request.user)
        if body.rx_only is not None:
            radio.set_rx_only(user, body.rx_only)
        if body.mute_minutes is not None:
            radio.silence(user, max(0, body.mute_minutes))
    except radio.AirError as error:
        _refuse(error)
    return _sign(radio.callsign_of(user))


def _station(row):
    return AirStation(id=row.pk, name=row.name, label=row.label, kind=row.kind)


@router.get("/stations", response=list[AirStation])
def stations(request):
    return [_station(row) for row in Station.objects.all()]


@router.post("/stations", response=AirStation)
def add_station(request, body: AirStationIn):
    name = body.name.strip().upper()
    if not radio._NAME.match(name):
        _refuse("Позывной: 2–12 латинских букв, цифр или дефисов, начинается с буквы.")
    if Station.objects.filter(name=name).exists() or Callsign.objects.filter(name=name).exists():
        _refuse(f"Позывной {name} уже занят.")
    if body.kind not in Station.Kind.values:
        _refuse("Вид: станция или персонаж.")
    return _station(Station.objects.create(name=name, label=body.label.strip()[:120], kind=body.kind))


@router.delete("/stations/{int:station_id}", response={204: None})
def delete_station(request, station_id: int):
    get_object_or_404(Station, pk=station_id).delete()
    return 204, None


def _band(row):
    return AirBand(id=row.pk, low=f"{row.low:.3f}", high=f"{row.high:.3f}", kind=row.kind, condition=row.condition, label=row.label,
                   window=row.window, time_zone=row.time_zone, open_now=events.propagation(row, chrono.game_now()))


def _zone(name):
    name = (name or "").strip() or "UTC"
    if not chrono.valid_zone(name):
        _refuse(f"Нет такого часового пояса: {name}. Пишите как Europe/Moscow.")
    return name


def _band_values(body):
    try:
        low, high = radio.parse_freq(body.low), radio.parse_freq(body.high)
    except radio.AirError as error:
        _refuse(error)
    if high < low:
        low, high = high, low
    if body.kind not in Band.Kind.values:
        _refuse("Вид полосы: обычная, зарезервирована или по условию.")
    try:
        windows.parse(body.window)
    except windows.WindowError as error:
        _refuse(f"Окно: {error}")
    return {"low": low, "high": high, "kind": body.kind, "condition": body.condition or None, "label": body.label.strip()[:120],
            "window": body.window.strip(), "time_zone": _zone(body.time_zone)}


@router.get("/bands", response=list[AirBand])
def bands(request):
    return [_band(row) for row in Band.objects.all()]


@router.post("/bands", response=AirBand)
def add_band(request, body: AirBandIn):
    return _band(Band.objects.create(**_band_values(body)))


@router.put("/bands/{int:band_id}", response=AirBand)
def change_band(request, band_id: int, body: AirBandIn):
    row = get_object_or_404(Band, pk=band_id)
    for name, value in _band_values(body).items():
        setattr(row, name, value)
    row.save()
    return _band(row)


@router.delete("/bands/{int:band_id}", response={204: None})
def delete_band(request, band_id: int):
    get_object_or_404(Band, pk=band_id).delete()
    return 204, None


@router.get("/reports", response=list[AirReport])
def reports(request):
    found = (Report.objects.filter(resolved_at=None).select_related("user", "transmission__user")
             .prefetch_related("user__socialaccount_set", "transmission__user__socialaccount_set").order_by("-created_at")[:200])
    return [AirReport(id=r.pk, transmission=_row(r.transmission), reporter=_player(r.user), reason=r.reason, at=r.created_at) for r in found]


@router.post("/reports/{int:report_id}/dismiss", response={204: None})
def dismiss(request, report_id: int):
    from django.utils import timezone

    Report.objects.filter(pk=report_id).update(resolved_at=timezone.now())
    return 204, None


# ---------- передачи по расписанию ----------

def _broadcast(row):
    try:
        summary = schedule.describe(schedule.parse(row.schedule))
    except schedule.ScheduleError:
        summary = ""
    return AirBroadcast(id=row.pk, station=row.station_id, freq=f"{row.freq:.3f}", texts=row.texts, schedule=row.schedule, time_zone=row.time_zone,
                        condition=row.condition, active=row.active, note=row.note, key=row.key, summary=summary, last_at=row.last_slot,
                        next_at=events.next_slot(row) if row.active else None)


def _broadcast_values(body):
    get_object_or_404(Station, pk=body.station)
    try:
        freq = radio.parse_freq(body.freq)
    except radio.AirError as error:
        _refuse(error)
    texts = [text.strip()[:400] for text in body.texts if text.strip()]
    if not texts:
        _refuse("Нужен хотя бы один текст передачи.")
    found = schedule.problems(body.schedule)
    if found:
        _refuse(f"Расписание: {found[0]}")
    return {"station_id": body.station, "freq": freq, "texts": texts, "schedule": body.schedule.strip(), "time_zone": _zone(body.time_zone),
            "condition": body.condition or None, "active": body.active, "note": body.note.strip()[:200], "key": cipher.normalize(body.key)}


@router.get("/broadcasts", response=list[AirBroadcast])
def broadcasts(request, station: int | None = None):
    rows = Broadcast.objects.all()
    if station:
        rows = rows.filter(station_id=station)
    return [_broadcast(row) for row in rows]


@router.post("/broadcasts", response=AirBroadcast)
def add_broadcast(request, body: AirBroadcastIn):
    return _broadcast(Broadcast.objects.create(**_broadcast_values(body)))


@router.put("/broadcasts/{int:broadcast_id}", response=AirBroadcast)
def change_broadcast(request, broadcast_id: int, body: AirBroadcastIn):
    row = get_object_or_404(Broadcast, pk=broadcast_id)
    values = _broadcast_values(body)
    if values["schedule"] != row.schedule or values["time_zone"] != row.time_zone:
        values["created_at"], values["last_slot"] = timezone.now(), None      # новое расписание: прошедшие слоты не выпускать
    for name, value in values.items():
        setattr(row, name, value)
    row.save()
    return _broadcast(row)


@router.post("/broadcasts/{int:broadcast_id}/now", response=AirRow)
def broadcast_now(request, broadcast_id: int):
    """Выпустить следующий текст сейчас, вне расписания (проверить, как звучит)."""
    row = get_object_or_404(Broadcast, pk=broadcast_id)
    text = row.texts[row.turn % len(row.texts)] if row.texts else ""
    try:
        sent = radio.station_transmit(row.station, row.freq, text, key=row.key)
    except radio.AirError as error:
        _refuse(error)
    sent.condition = row.condition
    sent.save(update_fields=["condition"])
    return _row(sent)


@router.delete("/broadcasts/{int:broadcast_id}", response={204: None})
def delete_broadcast(request, broadcast_id: int):
    get_object_or_404(Broadcast, pk=broadcast_id).delete()
    return 204, None


# ---------- ответчики ----------

ACTIONS = {"flag", "unflag", "key", "file", "letter", "hook"}


def _responder(row):
    return AirResponder(id=row.pk, station=row.station_id, freq=f"{row.freq:.3f}", pattern=row.pattern, regex=row.regex, condition=row.condition,
                        cooldown=row.cooldown, reply=row.reply, delay=row.delay, actions=row.actions or [], active=row.active, note=row.note,
                        key=row.key, fires=row.fires.count())


def _responder_values(body):
    get_object_or_404(Station, pk=body.station)
    try:
        freq = radio.parse_freq(body.freq)
    except radio.AirError as error:
        _refuse(error)
    found = events.pattern_problems(body.pattern, body.regex)
    if found:
        _refuse(f"Шаблон: {found[0]}")
    actions = [action for action in body.actions if action.get("do") in ACTIONS]
    if not body.reply.strip() and not actions:
        _refuse("Ответчику нужен ответ в эфир или хотя бы один исход.")
    return {"station_id": body.station, "freq": freq, "pattern": body.pattern.strip(), "regex": body.regex, "condition": body.condition or None,
            "cooldown": max(0, body.cooldown), "reply": body.reply.strip()[:400], "delay": max(0, min(body.delay, 86400)), "actions": actions,
            "active": body.active, "note": body.note.strip()[:200], "key": cipher.normalize(body.key)}


@router.get("/responders", response=list[AirResponder])
def responders(request, station: int | None = None):
    rows = Responder.objects.all()
    if station:
        rows = rows.filter(station_id=station)
    return [_responder(row) for row in rows]


@router.post("/responders", response=AirResponder)
def add_responder(request, body: AirResponderIn):
    return _responder(Responder.objects.create(**_responder_values(body)))


@router.put("/responders/{int:responder_id}", response=AirResponder)
def change_responder(request, responder_id: int, body: AirResponderIn):
    row = get_object_or_404(Responder, pk=responder_id)
    for name, value in _responder_values(body).items():
        setattr(row, name, value)
    row.save()
    return _responder(row)


@router.delete("/responders/{int:responder_id}", response={204: None})
def delete_responder(request, responder_id: int):
    get_object_or_404(Responder, pk=responder_id).delete()
    return 204, None


# ---------- мост с Discord ----------

class AirBridge(Schema):
    id: int
    freq: str
    channel_id: str
    label: str
    active: bool
    sent: int                  # ушло в Discord за сутки
    received: int              # пришло из Discord за сутки
    failed: int


class AirBridgeIn(Schema):
    freq: str
    channel_id: str
    label: str = ""
    active: bool = True


class AirBridgeStatus(Schema):
    token: bool
    online: bool
    bot: str
    seen_at: datetime | None
    error: str


class AirBridges(Schema):
    status: AirBridgeStatus
    links: list[AirBridge]


def _bridge(row):
    day = BridgeMessage.objects.filter(link=row, created_at__gte=timezone.now() - timedelta(days=1))
    return AirBridge(id=row.pk, freq=f"{row.freq:.3f}", channel_id=row.channel_id, label=row.label, active=row.active,
                     sent=day.filter(inbound=False, state=BridgeMessage.State.SENT).count(), received=day.filter(inbound=True).count(),
                     failed=day.filter(state=BridgeMessage.State.FAILED).count())


def _bridge_values(body, skip=None):
    try:
        freq = radio.parse_freq(body.freq)
    except radio.AirError as error:
        _refuse(error)
    channel = body.channel_id.strip()
    if not channel.isdigit() or not 15 <= len(channel) <= 22:
        _refuse("ID канала Discord: 17–20 цифр (в Discord: правой кнопкой по каналу → «Копировать ID канала»).")
    others = BridgeLink.objects.exclude(pk=skip)
    if others.filter(freq=freq).exists():
        _refuse(f"У частоты {freq} мост уже есть.")
    if others.filter(channel_id=channel).exists():
        _refuse("Этот канал уже связан с другой частотой.")
    return {"freq": freq, "channel_id": channel, "label": body.label.strip()[:120], "active": body.active}


@router.get("/bridges", response=AirBridges)
def bridges(request):
    from air import bridge

    return AirBridges(status=AirBridgeStatus(**bridge.status()), links=[_bridge(row) for row in BridgeLink.objects.all()])


@router.post("/bridges", response=AirBridge)
def add_bridge(request, body: AirBridgeIn):
    return _bridge(BridgeLink.objects.create(**_bridge_values(body)))


@router.put("/bridges/{int:bridge_id}", response=AirBridge)
def change_bridge(request, bridge_id: int, body: AirBridgeIn):
    row = get_object_or_404(BridgeLink, pk=bridge_id)
    for name, value in _bridge_values(body, skip=row.pk).items():
        setattr(row, name, value)
    row.save()
    return _bridge(row)


@router.delete("/bridges/{int:bridge_id}", response={204: None})
def delete_bridge(request, bridge_id: int):
    get_object_or_404(BridgeLink, pk=bridge_id).delete()
    return 204, None
