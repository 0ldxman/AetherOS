"""Что о машине и игроке известно из базы: для приветствия и других текстов, где подставляются значения.

Всё считается на лету из настоящих данных (учётки, события входа, сессии, тома), отдельно ничего не хранится."""
from datetime import timedelta

from django.utils import timezone

from machines.world import clock
from machines.models import LoginEvent, MachineMount, MachineProfile, Session, SystemVolume

ONLINE = timedelta(minutes=2)         # сессия считается живой, если терминал отмечался недавно


def uptime_text(delta):
    seconds = max(int(delta.total_seconds()), 0)
    days, rest = divmod(seconds, 86400)
    hours, minutes = divmod(rest // 60, 60)
    if days:
        return f"{days} day{'s' if days != 1 else ''}, {hours}:{minutes:02d}"
    if hours:
        return f"{hours}:{minutes:02d}"
    return f"{minutes} min"


def last_login(profile, user):
    """Предыдущий успешный вход на эту запись: самый свежий и есть текущий, поэтому берётся второй. Нет такого: never."""
    if profile is None:
        return "never"
    events = LoginEvent.objects.filter(profile=profile, kind=LoginEvent.Kind.OK)
    if user is not None:
        events = events.filter(user=user)
    previous = events.order_by("-at", "-id").values_list("shown_at", flat=True)[1:2]
    return timezone.localtime(previous[0]).strftime("%Y-%m-%d %H:%M") if previous else "never"


def volumes_text(machine):
    """Тома машины: «/ system, /mnt/harbor harbor» (образ ОС и свои монтирования, сеть не считается)."""
    rows = [(row.mount_path, row.volume.slug) for row in SystemVolume.objects.filter(system_type__code=machine.system).select_related("volume")]
    rows += [(m.mount_path, m.volume.slug) for m in MachineMount.objects.filter(machine=machine, mode="local").exclude(mount_path="").select_related("volume")]
    return ", ".join(f"{path} {slug}" for path, slug in sorted(set(rows)))


def facts(machine, profile=None, user=None):
    """Параметры приветствия, которые берутся из базы."""
    uptime = ""
    if machine.booted_at:
        uptime = uptime_text(clock.now(machine, user) - machine.booted_at)
    return {
        "accounts": machine.profiles.count(),
        "sessions": Session.objects.filter(profile__machine=machine, seen_at__gte=timezone.now() - ONLINE).count(),
        "last_login": last_login(profile, user),
        "uptime": uptime or "unknown",
        "note": machine.note,
        "volumes": volumes_text(machine) or "none",
        "freq": f"{profile.freq:.3f}" if profile is not None else None,
    }
