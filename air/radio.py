"""Правила эфира: частоты, позывные, передача, приём, скан, модерация.

Слушатель получает только передачи, пришедшие после его выхода на частоту (since): эфир не перематывается. Система хранит
передачи KEEP (24 часа) для модерации и скана, потом стирает. Песочный игрок автора слышит себя, но настоящие игроки его не слышат.
Тексты ошибок для игрока по-английски, как весь мир.
"""
import re
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db.models import Count, Max, Q
from django.utils import timezone

from air.models import Band, Callsign, CallsignChange, Report, Station, Transmission

LOW, HIGH, STEP = Decimal("3.000"), Decimal("30.000"), Decimal("0.005")
CALLING = Decimal("14.230")              # вызывной канал: его слышат все, включая гостей
MAX_TEXT = 280
KEEP = timedelta(hours=24)
GAP = timedelta(seconds=2)               # не чаще одной передачи в 2 секунды
PER_MINUTE = 20
SCAN_WIDTH = Decimal("0.500")
SCAN_WINDOW = timedelta(minutes=15)
RENAME_EVERY = timedelta(days=7)
NOISE = "··· noise ···"                  # так видна скрытая модератором передача
_NAME = re.compile(r"^[A-Z][A-Z0-9-]{1,11}$")
_LINK = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(?:com|net|org|ru|io|gg|me|xyz)\b\S*)", re.I)


class AirError(Exception):
    """Отказ эфира: текст для игрока."""


def parse_freq(value):
    """«14.23» -> Decimal('14.230'), привязанная к сетке STEP и проверенная на диапазон."""
    try:
        freq = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise AirError(f"bad frequency: {value}")
    if not freq.is_finite():
        raise AirError(f"bad frequency: {value}")
    freq = (freq / STEP).quantize(Decimal(1), rounding=ROUND_HALF_UP) * STEP
    freq = freq.quantize(Decimal("0.001"))
    if not LOW <= freq <= HIGH:
        raise AirError(f"frequency out of band: {LOW}-{HIGH} MHz")
    return freq


# ---------- позывные ----------

def _normalize(text):
    name = re.sub(r"[^A-Z0-9-]+", "-", (text or "").upper()).strip("-")
    name = re.sub(r"-{2,}", "-", name)
    if not name or not name[0].isalpha():
        name = "OP-" + name if name else "OP"
    return name[:12].strip("-") or "OP"


def _taken(name, user=None):
    if Station.objects.filter(name=name).exists():
        return True
    return Callsign.objects.filter(name=name).exclude(user=user).exists()


def _discord_name(user):
    account = next(iter(user.socialaccount_set.all()), None) if hasattr(user, "socialaccount_set") else None
    data = (account.extra_data or {}) if account is not None else {}
    return data.get("global_name") or data.get("username") or user.get_username()


def callsign_of(user):
    """Позывной игрока: создаётся при первом обращении из имени Discord (или логина), при совпадении с номером."""
    found = Callsign.objects.filter(user=user).first()
    if found is not None:
        return found
    base = _normalize(_discord_name(user))
    name, n = base, 1
    while _taken(name):
        n += 1
        name = f"{base[:12 - len(str(n)) - 1]}-{n}"
    return Callsign.objects.create(user=user, name=name)


def rename(user, new, by=None):
    """Сменить позывной. Игрок сам: не чаще раза в RENAME_EVERY. Автор (by): без ограничения."""
    sign = callsign_of(user)
    name = (new or "").strip().upper()
    if not _NAME.match(name):
        raise AirError("callsign: 2-12 letters, digits or '-', starting with a letter")
    if name == sign.name:
        return sign
    if _taken(name, user):
        raise AirError(f"callsign {name} is taken")
    now = timezone.now()
    if by is None and sign.changed_at is not None and now - sign.changed_at < RENAME_EVERY:
        raise AirError("callsign can be changed once a week")
    CallsignChange.objects.create(user=user, old=sign.name, new=name, by=by)
    sign.name = name
    if by is None:
        sign.changed_at = now
    sign.save()
    return sign


# ---------- полосы ----------

def band_of(freq):
    return Band.objects.filter(low__lte=freq, high__gte=freq).first()


def can_listen(freq, keys, guest=False):
    if guest:
        return freq == CALLING
    band = band_of(freq)
    if band is None or band.kind != Band.Kind.CONDITIONAL or not band.condition:
        return True
    from secure.access import satisfied

    return satisfied(band.condition, keys)


# ---------- передача ----------

def _clean(text):
    text = " ".join((text or "").split())
    text = _LINK.sub("", text)
    text = " ".join(text.split())
    if not text:
        raise AirError("nothing to transmit")
    if len(text) > MAX_TEXT:
        raise AirError(f"transmission longer than {MAX_TEXT} characters")
    return text


def transmit(user, freq, text, machine=None, now=None):
    """Передача игрока. Ошибки: AirError с текстом для игрока."""
    from users.sandbox import is_sandbox

    now = now or timezone.now()
    freq = parse_freq(freq)
    sign = callsign_of(user)
    if sign.rx_only:
        raise AirError("transmitter disabled")
    if sign.muted_until and sign.muted_until > now:
        raise AirError(f"transmitter silenced until {timezone.localtime(sign.muted_until):%H:%M}")
    band = band_of(freq)
    if band is not None and band.kind == Band.Kind.RESERVED:
        raise AirError(f"{freq} is a reserved band")
    text = _clean(text)
    mine = Transmission.objects.filter(user=user)
    last = mine.aggregate(last=Max("created_at"))["last"]
    if last is not None and now - last < GAP:
        raise AirError("transmitter cooling down")
    if mine.filter(created_at__gte=now - timedelta(minutes=1)).count() >= PER_MINUTE:
        raise AirError("too many transmissions, wait a minute")
    purge(now)
    return Transmission.objects.create(freq=freq, user=user, callsign=sign.name, machine=machine, text=text, sandbox=is_sandbox(user), created_at=now)


def station_transmit(station, freq, text):
    """Передача от станции или персонажа (Студия): без лимитов игрока, в любой полосе."""
    return Transmission.objects.create(freq=parse_freq(freq), station=station, callsign=station.name, text=_clean(text))


# ---------- приём ----------

def _audible(user):
    """Передачи, которые слышит этот слушатель: настоящие всем, песочные только своей песочнице."""
    visible = Q(sandbox=False)
    if user is not None:
        visible |= Q(sandbox=True, user=user)
    return Transmission.objects.filter(visible)


def listen(user, freq, since, after=0, now=None):
    """Принятое на частоте после выхода на неё (since) и после передачи after: [{id, callsign, station, text, at, hidden}]."""
    now = now or timezone.now()
    freq = parse_freq(freq)
    rows = _audible(user).filter(freq=freq, created_at__gte=max(since, now - KEEP), pk__gt=after).order_by("created_at", "pk")[:200]
    return [
        {"id": row.pk, "callsign": row.callsign, "station": row.station_id is not None, "text": NOISE if row.hidden_at else row.text,
         "at": row.created_at, "hidden": row.hidden_at is not None, "mine": user is not None and row.user_id == getattr(user, "pk", None)}
        for row in rows
    ]


def scan(user, low, high, now=None):
    """Где была активность за SCAN_WINDOW на участке до SCAN_WIDTH: [{freq, count, last}], без текста."""
    now = now or timezone.now()
    low, high = parse_freq(low), parse_freq(high)
    if high < low:
        low, high = high, low
    if high - low > SCAN_WIDTH:
        raise AirError(f"scan range wider than {SCAN_WIDTH} MHz")
    rows = (_audible(user).filter(freq__gte=low, freq__lte=high, created_at__gte=now - SCAN_WINDOW)
            .values("freq").annotate(count=Count("pk"), last=Max("created_at")).order_by("freq"))
    return [{"freq": row["freq"], "count": row["count"], "last": row["last"]} for row in rows]


# ---------- модерация ----------

def hide(transmission, by, reason=""):
    transmission.hidden_at, transmission.hidden_by, transmission.hidden_reason = timezone.now(), by, reason[:200]
    transmission.save(update_fields=["hidden_at", "hidden_by", "hidden_reason"])
    Report.objects.filter(transmission=transmission, resolved_at=None).update(resolved_at=timezone.now())


def unhide(transmission):
    transmission.hidden_at, transmission.hidden_by, transmission.hidden_reason = None, None, ""
    transmission.save(update_fields=["hidden_at", "hidden_by", "hidden_reason"])


def silence(user, minutes):
    sign = callsign_of(user)
    sign.muted_until = timezone.now() + timedelta(minutes=minutes) if minutes else None
    sign.save(update_fields=["muted_until"])
    return sign


def set_rx_only(user, value):
    sign = callsign_of(user)
    sign.rx_only = bool(value)
    sign.save(update_fields=["rx_only"])
    return sign


def report(transmission, user, reason=""):
    found, _ = Report.objects.get_or_create(transmission=transmission, user=user, defaults={"reason": reason[:200]})
    return found


def purge(now=None):
    """Стереть передачи старше KEEP (с их жалобами)."""
    return Transmission.objects.filter(created_at__lt=(now or timezone.now()) - KEEP).delete()[0]
