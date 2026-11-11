"""Эфир в Студии: живая лента всех частот, модерация, позывные с настоящими игроками, станции, полосы, жалобы. Логика в air/radio.py."""
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from air import radio
from air.models import Band, Callsign, CallsignChange, Report, Station, Transmission

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


class AirBandIn(Schema):
    low: str
    high: str
    kind: str = "reserved"
    condition: object = None
    label: str = ""


class AirTx(Schema):
    station: int
    freq: str
    text: str


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
        return _row(radio.station_transmit(get_object_or_404(Station, pk=body.station), body.freq, body.text))
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
    return AirBand(id=row.pk, low=f"{row.low:.3f}", high=f"{row.high:.3f}", kind=row.kind, condition=row.condition, label=row.label)


def _band_values(body):
    try:
        low, high = radio.parse_freq(body.low), radio.parse_freq(body.high)
    except radio.AirError as error:
        _refuse(error)
    if high < low:
        low, high = high, low
    if body.kind not in Band.Kind.values:
        _refuse("Вид полосы: зарезервирована или по условию.")
    return {"low": low, "high": high, "kind": body.kind, "condition": body.condition or None, "label": body.label.strip()[:120]}


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
