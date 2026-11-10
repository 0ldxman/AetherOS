"""Главная Студии: кто из игроков сейчас в мире, что в мире не так и (лентой, team/changes) что менялось."""
import datetime as dt

from django.utils import timezone
from ninja import Router, Schema

router = Router(tags=["dashboard"])


class DashPlayer(Schema):
    player: str
    login: str
    hostname: str
    machine: int
    seen_at: dt.datetime


class DashProblem(Schema):
    kind: str                    # machine | page | key | asset
    title: str
    text: str
    link: str


class DashOut(Schema):
    online: list[DashPlayer]
    problems: list[DashProblem]
    changes_today: int
    authors_today: int


@router.get("", response=DashOut)
def dashboard(request):
    from machines.models import Machine, Session
    from machines.world.facts import ONLINE
    from studio.api.machines import _warnings
    from team.models import Change
    from wiki import dashboard as wiki_dashboard

    sessions = (Session.objects.filter(seen_at__gte=timezone.now() - ONLINE)
                .select_related("user", "profile__machine").order_by("-seen_at")[:50])
    online = [DashPlayer(player=s.user.get_username(), login=s.profile.login, hostname=s.profile.machine.hostname,
                         machine=s.profile.machine_id, seen_at=s.seen_at) for s in sessions]

    problems = []
    for machine in Machine.objects.prefetch_related("profiles").order_by("hostname"):
        for warning in _warnings(machine, list(machine.profiles.all())):
            if warning.level == "warning":
                problems.append(DashProblem(kind="machine", title=machine.hostname or machine.name, text=warning.text,
                                            link=f"#/machines/{machine.pk}"))
    wiki = wiki_dashboard.build()
    for doc, path, count in wiki.broken[:20]:
        item = doc.item
        problems.append(DashProblem(kind="page", title=path.replace(":", "/"), text=f"Ошибок разметки: {count}.", link=f"#/items/{item.pk}"))
    if wiki.unused_keys:
        names = ", ".join(key.slug for key in wiki.unused_keys[:8])
        problems.append(DashProblem(kind="key", title=f"Ключей без применения: {len(wiki.unused_keys)}",
                                    text=f"Ни одно условие их не требует: {names}.", link="#/items"))

    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    changed = Change.objects.filter(at__gte=today)
    return DashOut(online=online, problems=problems, changes_today=changed.count(),
                   authors_today=changed.values("user").distinct().count())
