"""Игроки глазами автора: кто они, где были, что у них есть, и что автор может с ними сделать.

Игрок это пользователь игры (вход через Discord). Его учётки это записи машин, под которыми он работал (Session) или которые
привязаны к нему (рабочая учётка). Ключи игрока лежат файлами в папках секретов его учёток (filesystem.keystore), его
прогресс это слой игрока (PlayerFile: свои копии, удаления, корзина, снятые слои) и сдвиги часов машин (MachineClock).
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from machines.world.facts import ONLINE

RECENT_FILES = 30
RECENT_EVENTS = 40


class PlayerError(Exception):
    pass


def _discord(user):
    """Имя в Discord, если игрок входил через него."""
    account = next(iter(user.socialaccount_set.all()), None) if hasattr(user, "socialaccount_set") else None
    if account is None:
        return ""
    data = account.extra_data or {}
    return data.get("global_name") or data.get("username") or ""


def players(query="", online=False, limit=200):
    """Список игроков: последний вход, в мире ли сейчас, сколько учёток и изменённых файлов."""
    alive = timezone.now() - ONLINE
    found = get_user_model().objects.filter(is_superuser=False, sandbox_of__isnull=True).annotate(
        seen=Max("sessions__seen_at"),
        accounts=Count("sessions__profile", distinct=True),
        files=Count("player_files", distinct=True),
        online_now=Count("sessions", filter=Q(sessions__seen_at__gte=alive), distinct=True),
    ).prefetch_related("socialaccount_set")
    if query:
        found = found.filter(username__icontains=query)
    if online:
        found = found.filter(online_now__gt=0)
    return list(found.order_by("-seen", "username")[:limit])


def _accounts(user):
    """Учётки игрока: где он работал (сессии) и привязанные к нему, по одной строке на учётку."""
    from machines.access import entry
    from machines.models import MachineProfile
    from machines.network import bridge

    alive = timezone.now() - ONLINE
    seen = {}
    for session in user.sessions.select_related("profile__machine"):
        known = seen.get(session.profile_id)
        if known is None or (session.seen_at and (known["seen_at"] is None or session.seen_at > known["seen_at"])):
            seen[session.profile_id] = {"profile": session.profile, "seen_at": session.seen_at}
    for profile in MachineProfile.objects.filter(user=user).select_related("machine"):
        seen.setdefault(profile.pk, {"profile": profile, "seen_at": None})
    rows = []
    for row in seen.values():
        profile = row["profile"]
        rows.append({
            **row,
            "own": profile.user_id == user.pk,
            "online": bool(row["seen_at"] and row["seen_at"] >= alive),
            "locked": max(bridge.locked_for(user, profile), entry.locked_seconds(user, profile)),
        })
    rows.sort(key=lambda r: (r["seen_at"] is None, -(r["seen_at"].timestamp() if r["seen_at"] else 0), r["profile"].login))
    return rows


def _keys(user, accounts):
    from filesystem import keystore
    from filesystem.machine_view import view_for

    rows = []
    for row in accounts:
        profile = row["profile"]
        view = view_for(profile.machine, user)
        for name, slug in keystore.held(view, profile.machine, profile.login):
            rows.append({"profile": profile, "name": name, "slug": slug})
    return rows


def _files(user):
    from filesystem.models import PlayerFile

    found = PlayerFile.objects.filter(user=user).select_related("instance__host", "instance__volume", "item")
    per_machine = {}
    for host_id, hostname, count in found.values_list("instance__host_id", "instance__host__hostname").annotate(count=Count("pk")):
        per_machine[host_id] = {"machine": host_id, "hostname": hostname, "count": count}
    recent = []
    for row in found.order_by("-updated_at")[:RECENT_FILES]:
        if row.trashed_at:
            kind = "в корзине"
        elif row.deleted_at:
            kind = "удалён"
        elif row.item_id is None:
            kind = "свой файл"
        elif row.content is not None or row.data is not None:
            kind = "правка"
        elif row.state:
            kind = "снятые слои"
        else:
            kind = "копия"
        recent.append({"hostname": row.instance.host.hostname, "volume": row.instance.volume.slug, "path": "/" + row.path.lstrip("/"),
                       "kind": kind, "at": row.updated_at})
    return sorted(per_machine.values(), key=lambda r: r["hostname"]), recent


def card(user):
    from machines.models import LoginEvent

    accounts = _accounts(user)
    per_machine, recent = _files(user)
    events = LoginEvent.objects.filter(user=user).select_related("profile__machine").order_by("-at", "-id")[:RECENT_EVENTS]
    return {
        "user": user, "discord": _discord(user), "accounts": accounts, "keys": _keys(user, accounts),
        "machines": per_machine, "files": recent, "events": list(events),
        "online": any(row["online"] for row in accounts),
    }


def _profile_of(user, profile_id):
    from machines.models import MachineProfile

    profile = MachineProfile.objects.select_related("machine").filter(pk=profile_id).first()
    if profile is None or not (profile.user_id == user.pk or user.sessions.filter(profile=profile).exists()):
        raise PlayerError("Это не учётка игрока.")
    return profile


def kick(user, profile_id):
    from machines.network import bridge

    return bridge.request_kick(user, _profile_of(user, profile_id))


def unlock(user, profile_id):
    from machines.access import entry

    entry.unlock(_profile_of(user, profile_id), user)


def give_key(user, profile_id, slug):
    """Положить ключ в папку секретов учётки игрока. Возвращает путь файла."""
    from filesystem import keystore
    from filesystem.machine_view import view_for
    from secure.keys import key_items

    profile = _profile_of(user, profile_id)
    item = key_items().filter(slug=slug).first()
    if item is None:
        raise PlayerError(f"Ключа «{slug}» нет в реестре.")
    if not keystore.secrets_dir(profile.machine, profile.login):
        raise PlayerError("У этой учётки нет папки секретов.")
    path, made = keystore.put(view_for(profile.machine, user), profile.machine, profile.login, item)
    if not made:
        raise PlayerError("Этот ключ у игрока уже есть.")
    return path


def take_key(user, profile_id, name):
    """Забрать ключ: файл из папки секретов учётки игрока удаляется в его слое (у остальных он не меняется)."""
    from filesystem import keystore
    from filesystem.machine_view import view_for

    profile = _profile_of(user, profile_id)
    folder = keystore.secrets_dir(profile.machine, profile.login)
    view = view_for(profile.machine, user)
    if not folder or name not in {held for held, _ in keystore.held(view, profile.machine, profile.login)}:
        raise PlayerError("Такого ключа у игрока нет.")
    view.remove(f"{folder}/{name}")


@transaction.atomic
def reset(user, machine_id=None):
    """Сбросить прогресс игрока: его файлы (копии, правки, удаления, корзина, снятые слои) и сдвиги часов, на машине или везде.

    Возвращает число убранных файлов. Учётки, сессии и журнал входов не трогаются."""
    from filesystem.models import PlayerFile
    from machines.models import MachineClock

    files = PlayerFile.objects.filter(user=user)
    clocks = MachineClock.objects.filter(user=user)
    if machine_id is not None:
        files = files.filter(instance__host_id=machine_id)
        clocks = clocks.filter(machine_id=machine_id)
    count = files.count()
    files.delete()
    clocks.delete()
    return count


def ban(actor, user, banned):
    """Отключить вход (или вернуть): неактивный пользователь не входит, а открытые подключения закрываются."""
    from machines.models import Session

    if user.is_superuser or user.pk == actor.pk:
        raise PlayerError("Суперадмину и себе вход не отключить.")
    user.is_active = not banned
    user.save(update_fields=["is_active"])
    if banned:
        Session.objects.filter(user=user).update(kick_at=timezone.now())
