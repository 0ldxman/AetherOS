"""Где у игрока лежит объект: его копии на машинах, где у игрока есть учётка.

Ищется по самому объекту, а не по пути: перенос и переименование файла его не теряют, копия (cp) — ещё одна запись.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Copy:
    host: str
    path: str
    trashed: bool           # лежит в корзине
    edited: bool            # игрок поменял текст
    progress: str = ""      # прогресс игрока по слоям (PlayerFile.state)


def accounts(user, machine=None):
    """[(машина, логин)] игрока: его сессии и привязанные к нему учётки (machine — только эта машина)."""
    from machines.models import MachineProfile, Session

    sessions = Session.objects.filter(user=user).select_related("profile__machine")
    profiles = MachineProfile.objects.filter(user=user).select_related("machine")
    if machine is not None:
        sessions, profiles = sessions.filter(profile__machine=machine), profiles.filter(machine=machine)
    found = {}
    for profile in [row.profile for row in sessions] + list(profiles):
        found.setdefault((profile.machine_id, profile.login), profile)
    return [(profile.machine, login) for (_, login), profile in found.items()]


def copies(user, slug, machine=None):
    """Копии объекта slug у игрока user (на машине machine или на всех его машинах), по пути."""
    from filesystem.machine_view import view_for

    out = {}
    for host, login in accounts(user, machine):
        view = view_for(host, user, login=login)
        for entry in view.entries.values():
            if entry.is_dir or entry.via is not None or entry.item is None or entry.item.slug != slug:
                continue
            player = entry.player
            out.setdefault((host.hostname, entry.path), Copy(
                host.hostname, entry.path,
                trashed=player is not None and player.trashed_at is not None,
                edited=player is not None and (player.content is not None or player.data is not None), progress=entry.progress or ""))
    return sorted(out.values(), key=lambda c: (c.trashed, c.host, c.path))
