"""Сессии игроков в графе: «Сессия: Текущая / Все / Машина» и сущность «Сессия».

Сессия — пара игрок + учётка (machines.models.Session): заводится при первом входе и остаётся. По проводу едет ключом
«игрок/логин@хост». Текущая — где произошло действие (машина и учётка события; в условии у «Изменить» — где игрок применяет
возможность). Активна — рабочий стол или терминал игрока там; подключена — открыта в цепочке мостов (machines.network.bridge):
закрытая сессия удаляется.
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


def online_users():
    """Игроки, которые сейчас в игре (активная сессия где угодно)."""
    from django.contrib.auth import get_user_model

    return list(get_user_model().objects.filter(session__seen_at__gte=_since(), sandbox_of__isnull=True).distinct().order_by("username"))


def audience(items):
    """[(игрок, где)] по тому, что подали: игрок (логин; где угодно), сессия (игрок/логин@хост; на её учётке), учётка (логин@хост) или
    машина (хост) — те, кто сейчас на них, там же. Где — для engine/push. Игрок повторно не попадает, непонятное пропускается."""
    from engine.push import where_of
    from django.contrib.auth import get_user_model

    from graph import entities
    from machines.models import Session
    from machines.world import edits

    User = get_user_model()
    since, found = _since(), []
    for raw in items:
        key = str(raw or "").strip()
        if not key:
            continue
        where = ""
        if "/" in key:
            parsed = parse(key)
            profile = edits.account(f"{parsed[1]}@{parsed[2]}") if parsed else None
            users = list(User.objects.filter(username=parsed[0])) if parsed and profile is not None else []
            where = where_of(profile)
        elif "@" in key:
            profile = edits.account(key)
            users = [row.user for row in Session.objects.filter(profile=profile, seen_at__gte=since).select_related("user")] if profile else []
            where = where_of(profile)
        else:
            users = list(User.objects.filter(username__iexact=key))
            if not users:
                machine = entities._machine(key)
                users = [row.user for row in Session.objects.filter(profile__machine=machine, seen_at__gte=since).select_related("user")] \
                    if machine is not None else []
                where = where_of(machine=machine)
        for user in users:
            if all(user != seen for seen, _ in found) and getattr(user, "sandbox_of_id", None) is None:
                found.append((user, where))
    return found


def of_machine(machine, active=False):
    """Сессии всех игроков на машине: список ключей, свежие первыми."""
    from machines.models import Session

    rows = Session.objects.select_related("user", "profile__machine").filter(profile__machine=machine, user__sandbox_of__isnull=True)
    return _keys(rows.filter(seen_at__gte=_since()) if active else rows)


def of_account(profile, active=False):
    """Сессии игроков на учётке: список ключей, свежие первыми."""
    from machines.models import Session

    rows = Session.objects.select_related("user", "profile__machine").filter(profile=profile, user__sandbox_of__isnull=True)
    return _keys(rows.filter(seen_at__gte=_since()) if active else rows)


def _keys(rows):
    rows = sorted(rows, key=lambda row: (row.seen_at is None, -(row.seen_at.timestamp() if row.seen_at else 0), row.pk))
    return list(dict.fromkeys(key_of(row.user.get_username(), row.profile.login, row.profile.machine.hostname) for row in rows))


def close(run, keys):
    """«Сессия: Закрыть»: выбросить игроков с учёток по ключам (пусто — текущая). Сколько сессий помечено."""
    from django.contrib.auth import get_user_model

    from machines.models import MachineProfile
    from machines.network import bridge

    keys = [key for key in keys if str(key or "").strip()] or [find(run, "current")]
    count = 0
    for key in keys:
        found = parse(key)
        if found is None:
            continue
        username, login, host = found
        user = get_user_model().objects.filter(username=username).first()
        profile = MachineProfile.objects.filter(machine__hostname=host, login=login).first()
        if user is not None and profile is not None:
            count += bridge.request_kick(user, profile)
    return count


def find(run, mode, player="", machine="", active=False, account=""):
    """Текущая — ключ; Все (сессии игрока), Машина (сессии на машине), Учётка (сессии на учётке) — список ключей, свежие первыми."""
    from graph import entities
    from machines.models import Session

    if mode == "account":
        from machines.world import edits

        profile = edits.account(entities._key(account))
        return of_account(profile, active) if profile is not None else []
    if mode not in ("all", "machine"):
        ctx, user = run.ctx or {}, getattr(run, "user", None)
        return key_of(user.get_username() if user is not None else "", ctx.get("login") or "", ctx.get("host") or "")
    rows = Session.objects.select_related("user", "profile__machine")
    if mode == "machine":
        found = entities._machine(entities._key(machine))
        return of_machine(found, active) if found is not None else []
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
    from machines.models import Workplace

    since = _since()
    active = bool(row and row.seen_at and row.seen_at >= since)
    where = ""
    if row is not None:
        place = Workplace.objects.filter(user_id=row.user_id).values_list("desktop_id", "terminal_id").first() or (None, None)
        where = {(True, True): "стол и терминал", (True, False): "стол", (False, True): "терминал"}.get((place[0] == row.pk, place[1] == row.pk), "")
    return {"value": key_of(username, login, host), "player": username, "machine": host, "account": f"{login}@{host}",
            "seen": times.of_real(row.seen_at) if row is not None else "", "active": active, "linked": row is not None,
            "status": "активна" if active else "подключена" if row is not None else "закрыта", "via": row.via if row is not None else "",
            "where": where}
