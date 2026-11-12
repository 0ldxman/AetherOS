"""air: радиоэфир из терминала (air/radio.py). Тот же эфир, что в приложении, но свой приёмник: терминал помнит свою частоту
и время выхода на неё в сессии, и air log показывает только принятое после этого."""
from datetime import datetime

from django.utils import timezone

from air import radio
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.result import CommandResult

TUNE_KEY = "air_term_tune"
CIPHER = "air_term_keys"           # ключ шифра терминала на каждой частоте
USAGE = "usage: air [tune <MHz> | tx <text> | log [n] | scan <from> <to> | call [callsign]]"


def _session(context):
    request = getattr(context, "request", None)
    return getattr(request, "session", None)


def _keys(context):
    request = getattr(context, "request", None)
    if request is None:
        return set()
    from secure.requestkeys import request_keys

    return request_keys(request)


def _hhmm(moment, machine=None):
    from machines.world import chrono

    return chrono.stamp(moment, machine, "%H:%M:%S")


class AirCommand(BaseCommand):
    name = "air"

    def execute(self, context, args):
        user = getattr(context.session, "user", None)
        sub, rest = (args[0], args[1:]) if args else ("", [])
        try:
            if sub == "":
                return self._status(context, user)
            if sub == "tune":
                return self._tune(context, user, rest)
            if sub == "tx":
                return self._tx(context, user, rest)
            if sub == "log":
                return self._log(context, user, rest)
            if sub == "scan":
                return self._scan(context, user, rest)
            if sub == "call":
                return self._call(user, rest)
            if sub == "key":
                return self._key(context, rest)
        except radio.AirError as error:
            return CommandResult(f"air: {error}", 1)
        return CommandResult(USAGE, 2)

    # приёмник терминала: частота и время прихода в сессии
    def _tuned(self, context):
        session = _session(context)
        found = session.get(TUNE_KEY) if session is not None else None
        if not found:
            return self._set(context, radio.CALLING)
        return radio.parse_freq(found["freq"]), datetime.fromisoformat(found["since"])

    def _set(self, context, freq):
        since = timezone.now()
        session = _session(context)
        if session is not None:
            session[TUNE_KEY] = {"freq": str(freq), "since": since.isoformat()}
        return freq, since

    def _status(self, context, user):
        freq, since = self._tuned(context)
        who = radio.callsign_of(user).name if user is not None else "listener (sign in to transmit)"
        return CommandResult(f"rx {freq:.3f} MHz since {_hhmm(since, context.machine)}\ncallsign {who}")

    def _tune(self, context, user, rest):
        if len(rest) != 1:
            return CommandResult("usage: air tune <MHz>", 2)
        freq = radio.parse_freq(rest[0])
        if not radio.can_listen(freq, _keys(context), guest=user is None):
            raise radio.AirError("no carrier on this frequency" if user is not None else "guests can only listen on the calling channel")
        freq, _since = self._set(context, freq)
        return CommandResult(f"rx {freq:.3f} MHz")

    def _tx(self, context, user, rest):
        if user is None:
            raise radio.AirError("sign in to transmit")
        if not rest:
            return CommandResult("usage: air tx <text>", 2)
        freq, _since = self._tuned(context)
        radio.transmit(user, freq, " ".join(rest), machine=context.machine, keys=_keys(context), air_key=self._cipher(context, freq))
        return CommandResult(f"tx {freq:.3f} MHz ok")

    def _log(self, context, user, rest):
        if len(rest) > 1 or (rest and not rest[0].isdigit()):
            return CommandResult("usage: air log [n]", 2)
        count = int(rest[0]) if rest else 20
        freq, since = self._tuned(context)
        rows = radio.listen(user, freq, since, keys=_keys(context), air_key=self._cipher(context, freq))[-count:] if count else []
        if not rows:
            return CommandResult(f"no traffic on {freq:.3f} since {_hhmm(since, context.machine)}")
        width = max(len(row["callsign"]) for row in rows)
        return CommandResult("\n".join(f"{_hhmm(row['at'], context.machine)}  {row['callsign']:<{width}}  {row['text']}" for row in rows))

    def _scan(self, context, user, rest):
        if len(rest) != 2:
            return CommandResult("usage: air scan <from MHz> <to MHz>", 2)
        from air.views import SCAN_EVERY, SCAN_KEY

        now = timezone.now()
        session = _session(context)
        last = session.get(SCAN_KEY) if session is not None else None
        if last and now - datetime.fromisoformat(last) < SCAN_EVERY:
            raise radio.AirError("scanner busy, try again in a few seconds")
        rows = radio.scan(user, rest[0], rest[1], now=now, keys=_keys(context))
        if session is not None:
            session[SCAN_KEY] = now.isoformat()
        keys = _keys(context)
        rows = [row for row in rows if radio.can_listen(row["freq"], keys, guest=user is None)]
        if not rows:
            return CommandResult(f"no activity in {radio.parse_freq(rest[0]):.3f}-{radio.parse_freq(rest[1]):.3f}")
        lines = []
        for row in rows:
            minutes = int((now - row["last"]).total_seconds() // 60)
            lines.append(f"{row['freq']:.3f}  {row['count']:>3} tx  {'just now' if not minutes else f'{minutes} min ago'}")
        return CommandResult("\n".join(lines))

    def _cipher(self, context, freq):
        session = _session(context)
        return (session.get(CIPHER, {}) if session is not None else {}).get(f"{freq:.3f}", "")

    def _key(self, context, rest):
        """air key — показать ключ этой частоты, air key <слово> — задать, air key - — снять."""
        from air import cipher

        freq, _since = self._tuned(context)
        session = _session(context)
        found = dict(session.get(CIPHER, {})) if session is not None else {}
        if not rest:
            current = found.get(f"{freq:.3f}", "")
            return CommandResult(f"key on {freq:.3f}: {current}" if current else f"no key on {freq:.3f}")
        key = "" if rest == ["-"] else cipher.normalize(" ".join(rest))
        if rest != ["-"] and not key:
            raise radio.AirError("a key needs at least one letter or digit")
        if key:
            found[f"{freq:.3f}"] = key
        else:
            found.pop(f"{freq:.3f}", None)
        if session is not None:
            session[CIPHER] = found
        return CommandResult(f"key on {freq:.3f}: {key}" if key else f"key removed on {freq:.3f}")

    def _call(self, user, rest):
        if user is None:
            raise radio.AirError("sign in to get a callsign")
        if len(rest) > 1:
            return CommandResult("usage: air call [callsign]", 2)
        sign = radio.rename(user, rest[0]) if rest else radio.callsign_of(user)
        return CommandResult(f"callsign {sign.name}")
