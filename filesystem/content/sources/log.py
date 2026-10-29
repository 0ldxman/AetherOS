"""Журнал входов хоста: файл формата log строится из событий входа (machines.LoginEvent) на машине, где он лежит.

Игрок читает только то, что касается его самого: события, которые породили его входы. Так /var/log/auth.log и улика, и след,
который игрок оставляет на чужих машинах.
"""
from django.utils import timezone

from filesystem.content.sources.base import Payload, Source, text_window

LOG_FORMAT = "log"
LINES = 300

PHRASES = {
    "ok": "Accepted {method} for {login} from {source}",
    "bad_password": "Failed password for {login} from {source}",
    "bad_key": "Failed publickey for {login} from {source}",
    "bad_token": "Failed token for {login} from {source}",
    "source": "Refused {login} from {source}: source not allowed",
    "route": "Refused {login} from {source}: wrong route",
    "window": "Refused {login} from {source}: outside permitted hours",
    "locked": "Account {login} locked after repeated failures",
}


def render(machine, user):
    """Строки журнала машины для игрока: по одной на событие, старые первыми."""
    from machines.models import LoginEvent

    if machine is None or user is None:
        return "", "empty"
    events = list(LoginEvent.objects.filter(profile__machine=machine, user=user).select_related("profile").order_by("-at", "-id")[:LINES])[::-1]
    host = machine.hostname or machine.name
    lines = [
        f"{timezone.localtime(event.shown_at):%Y-%m-%d %H:%M:%S} {host} auth: "
        + PHRASES.get(event.kind, event.kind).format(login=event.profile.login, source=event.source or "local", method=event.detail or "password")
        for event in events
    ]
    last = events[-1].pk if events else 0
    return "\n".join(lines) + ("\n" if lines else ""), f"{len(events)}:{last}"


class LogSource(Source):
    name = "log"

    def accepts(self, entry):
        return entry.item is not None and entry.item.format == LOG_FORMAT

    def payload(self, entry, view, keys, reader, viewer):
        machine = entry.machine or (view.machine if view is not None else None)
        text, mark = render(machine, view.user if view is not None else None)
        return Payload(kind="log", layout="raw", body=text.encode(), real=False, stamp=f"log:{entry.item.pk}:{mark}")

    def window(self, entry, address):
        return text_window(address)
