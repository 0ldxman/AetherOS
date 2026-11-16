"""Сессии игроков в графе: «Сессия: Текущая / Все / Машина» и сущность «Сессия».

Сессия — пара игрок + учётка (machines.models.Session): заводится при первом входе и остаётся. По проводу едет ключом
«игрок/логин@хост». Текущая — где произошло действие (машина и учётка события; в условии у «Изменить» — где игрок применяет
возможность). Активна — рабочий стол или терминал игрока там; подключена — открыта в цепочке мостов (machines.network.bridge).
"""
from django.utils import timezone


def key_of(username, login, host):
    return f"{username}/{login}@{host}" if username and login and host else ""


def parse(key):
    """(игрок, логин, хост) или None."""
    username, sep, account = str(key or "").strip().partition("/")
    login, _, host = account.rpartition("@")
    return (username, login, host) if sep and username and login and host else None


def _since():
    from machines.world.facts import ONLINE

    return timezone.now() - ONLINE


def find(run, mode, player="", machine="", active=False):
    """Текущая — ключ; Все (сессии игрока) и Машина (сессии на машине) — список ключей, свежие первыми."""
    from graph import entities
    from machines.models import Session

    if mode not in ("all", "machine"):
        ctx, user = run.ctx or {}, getattr(run, "user", None)
        return key_of(user.get_username() if user is not None else "", ctx.get("login") or "", ctx.get("host") or "")
    rows = Session.objects.select_related("user", "profile__machine")
    if mode == "machine":
        found = entities._machine(entities._key(machine))
        if found is None:
            return []
        rows = rows.filter(profile__machine=found, user__sandbox_of__isnull=True)
    else:
        user = entities._player(run, entities._key(player))
        if user is None:
            return []
        rows = rows.filter(user=user)
    if active:
        rows = rows.filter(seen_at__gte=_since())
    rows = sorted(rows, key=lambda row: (row.seen_at is None, -(row.seen_at.timestamp() if row.seen_at else 0), row.pk))
    return list(dict.fromkeys(key_of(row.user.get_username(), row.profile.login, row.profile.machine.hostname) for row in rows))


def props(key):
    """Выходы сущности «Сессия» по ключу или None."""
    from machines.models import Session

    found = parse(key)
    if found is None:
        return None
    username, login, host = found
    row = (Session.objects.filter(user__username__iexact=username, profile__login=login, profile__machine__hostname__iexact=host)
           .order_by("-pk").first())
    from graph import times

    since = _since()
    return {"value": key_of(username, login, host), "player": username, "machine": host, "account": f"{login}@{host}",
            "seen": times.of_real(row.seen_at) if row is not None else "",
            "active": bool(row and row.seen_at and row.seen_at >= since), "linked": bool(row and row.linked_at and row.linked_at >= since)}
