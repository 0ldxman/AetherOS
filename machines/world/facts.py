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


def _mounted(machine):
    """Тома машины с точками: образ ОС и свои локальные монтирования (сеть не считается)."""
    rows = [(row.mount_path, row.volume) for row in SystemVolume.objects.filter(system_type__code=machine.system).select_related("volume") if row.mount_path]
    rows += [(m.mount_path, m.volume) for m in MachineMount.objects.filter(machine=machine, mode="local").exclude(mount_path="").select_related("volume")]
    return rows


def volumes_text(machine):
    """Тома машины: «/ system, /mnt/harbor harbor»."""
    return ", ".join(f"{path} {volume.slug}" for path, volume in sorted({(path, volume.pk): (path, volume) for path, volume in _mounted(machine)}.values(), key=lambda r: r[0]))


def size_text(gb):
    """Условный размер: «512 GB», «4 TB», «1.5 TB»."""
    if gb < 1000:
        return f"{gb} GB"
    tera = gb / 1000
    return f"{tera:.0f} TB" if tera >= 10 or tera == int(tera) else f"{tera:.1f} TB"


def disks_text(machine):
    """Условный объём дисков машины по томам, у которых он задан: (всего, занято, процент) строками или None, если нигде не задан."""
    found = {volume.pk: volume for _, volume in _mounted(machine) if volume.capacity_gb}
    total = sum(volume.capacity_gb for volume in found.values())
    if not total:
        return None
    used = sum(volume.used_gb or 0 for volume in found.values())
    return size_text(total), size_text(used), f"{round(used * 100 / total)}"


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
        **dict(zip(("disk_total", "disk_used", "disk_percent"), disks_text(machine) or ("unknown", "unknown", "?"))),
        "freq": f"{profile.freq:.3f}" if profile is not None else None,
    }
