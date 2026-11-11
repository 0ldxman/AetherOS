"""Приложение «эфир» у игрока: приёмник на одной частоте. Выход на частоту запоминается в сессии (частота и время прихода):
слышно только то, что пришло после него. Новое открытие приложения начинает приём заново."""
import json
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from air import radio
from air.models import Transmission

TUNE_KEY = "air_tune"            # {"freq": "14.230", "since": iso}
SCAN_KEY = "air_scanned_at"
SCAN_EVERY = timedelta(seconds=10)


def _player(request):
    return request.user if request.user.is_authenticated else None


def _keys(request):
    from secure.requestkeys import request_keys

    return request_keys(request)


def _tune(request, freq):
    """Выйти на частоту сейчас: прежний приём забывается."""
    request.session[TUNE_KEY] = {"freq": str(freq), "since": timezone.now().isoformat()}


def _tuned(request):
    found = request.session.get(TUNE_KEY)
    if not found:
        _tune(request, radio.CALLING)
        found = request.session[TUNE_KEY]
    return radio.parse_freq(found["freq"]), datetime.fromisoformat(found["since"])


def _state(request):
    freq, since = _tuned(request)
    player = _player(request)
    return {"freq": f"{freq:.3f}", "since": since.isoformat(), "callsign": radio.callsign_of(player).name if player else "",
            "can_tx": player is not None, "calling": f"{radio.CALLING:.3f}"}


def _row(row):
    return {**row, "at": timezone.localtime(row["at"]).strftime("%H:%M:%S")}


def _error(error, status=400):
    return JsonResponse({"error": str(error)}, status=status)


@ensure_csrf_cookie
def index(request):
    freq = request.session.get(TUNE_KEY, {}).get("freq") or radio.CALLING
    if not radio.can_listen(radio.parse_freq(freq), _keys(request), guest=_player(request) is None):
        freq = radio.CALLING
    _tune(request, freq)                                          # открыли приложение: приём с чистого листа
    return render(request, "air/index.html", {"state": _state(request)})


@require_POST
def tune(request):
    try:
        freq = radio.parse_freq(json.loads(request.body or b"{}").get("freq", ""))
    except radio.AirError as error:
        return _error(error)
    if not radio.can_listen(freq, _keys(request), guest=_player(request) is None):
        return _error("no carrier on this frequency" if _player(request) else "guests can only listen on the calling channel", 403)
    _tune(request, freq)
    return JsonResponse(_state(request))


@require_GET
def listen(request):
    freq, since = _tuned(request)
    after = int(request.GET.get("after") or 0) if str(request.GET.get("after") or "0").isdigit() else 0
    rows = radio.listen(_player(request), freq, since, after)
    return JsonResponse({"freq": f"{freq:.3f}", "rows": [_row(row) for row in rows]})


@require_POST
def transmit(request):
    player = _player(request)
    if player is None:
        return _error("sign in to transmit", 403)
    from machines.current import current_machine

    freq, _since = _tuned(request)
    text = json.loads(request.body or b"{}").get("text", "")
    try:
        sent = radio.transmit(player, freq, text if isinstance(text, str) else "", machine=current_machine(request))
    except radio.AirError as error:
        return _error(error)
    return JsonResponse({"id": sent.pk})


@require_GET
def scan(request):
    now = timezone.now()
    last = request.session.get(SCAN_KEY)
    if last and now - datetime.fromisoformat(last) < SCAN_EVERY:
        return _error("scanner busy, try again in a few seconds", 429)
    try:
        found = radio.scan(_player(request), request.GET.get("low", ""), request.GET.get("high", ""), now=now)
    except radio.AirError as error:
        return _error(error)
    request.session[SCAN_KEY] = now.isoformat()
    keys, guest = _keys(request), _player(request) is None
    return JsonResponse({"rows": [
        {"freq": f"{row['freq']:.3f}", "count": row["count"], "ago": int((now - row["last"]).total_seconds() // 60)}
        for row in found if radio.can_listen(row["freq"], keys, guest=guest)
    ]})


@require_POST
def callsign(request):
    player = _player(request)
    if player is None:
        return _error("sign in to get a callsign", 403)
    try:
        sign = radio.rename(player, json.loads(request.body or b"{}").get("name", ""))
    except radio.AirError as error:
        return _error(error)
    return JsonResponse({"callsign": sign.name})


@require_POST
def report(request):
    player = _player(request)
    if player is None:
        return _error("sign in to report", 403)
    data = json.loads(request.body or b"{}")
    found = get_object_or_404(Transmission, pk=int(data.get("id") or 0))
    radio.report(found, player, str(data.get("reason") or ""))
    return JsonResponse({"ok": True})
