"""Раздачи игроков: папку из своего дома игрок отдаёт по имени и коду (share); другой подключает её к себе в дом (mnt) или к вики.
Режим ro — только смотреть и копировать; drop — ещё класть новое, а удалять и менять только то, что положил сам."""
import posixpath
import re
import secrets

from machines.models import PlayerMount, Share


class ShareError(Exception):
    pass


def _slug(text):
    return re.sub(r"[^a-z0-9._-]+", "-", str(text or "").lower()).strip("-.")[:64]


def new_code():
    raw = secrets.token_hex(4)
    return f"{raw[:4]}-{raw[4:]}"


def inside_home(view, profile, path, own_folder=False):
    """path в доме учётки: сам дом (own_folder=False) или что-то внутри него."""
    path = "/" + path.strip("/")
    probe = posixpath.dirname(path) if own_folder else path
    return path != "/" and view.home_owner(probe) == profile.login


def share(view, profile, path, mode="ro", name=""):
    """Раздать папку path из дома учётки profile. Та же папка уже раздана — меняется режим, код прежний. Возвращает Share."""
    path = "/" + path.strip("/")
    if mode not in Share.Mode.values:
        raise ShareError(f"unknown mode '{mode}'")
    if not inside_home(view, profile, path):
        raise ShareError(f"{path}: only folders of your home can be shared")
    if not view.is_directory(path):
        raise ShareError(f"{path}: not a directory")
    found = Share.objects.filter(profile=profile, path=path).first()
    if found is not None:
        found.mode = mode
        found.save(update_fields=["mode"])
        return found
    name = _slug(name) or _slug(f"{profile.login}-{posixpath.basename(path)}")
    if not name:
        raise ShareError("bad name")
    if Share.objects.filter(machine=profile.machine, name=name).exists():
        raise ShareError(f"name '{name}' is taken")
    return Share.objects.create(machine=profile.machine, profile=profile, name=name, path=path, code=new_code(), mode=mode)


def find(host, name):
    return Share.objects.filter(machine__hostname__iexact=host, name__iexact=name).select_related("machine", "profile").first()


def unshare(profile, what):
    """Закрыть раздачу по имени или папке: подключения у всех пропадают. Возвращает сколько закрыто."""
    what = str(what or "").strip()
    rows = Share.objects.filter(profile=profile)
    rows = rows.filter(path="/" + what.strip("/")) if what.startswith("/") else rows.filter(name__iexact=what)
    count = rows.delete()[0]
    _changed()
    return count


def mount(view, user, profile, share_row, code, point):
    """Подключить раздачу к себе в дом: point — папка внутри дома учётки profile. Возвращает PlayerMount."""
    if share_row is None or share_row.code != code:
        raise ShareError("no such share or wrong code")
    point = "/" + point.strip("/")
    if not inside_home(view, profile, point, own_folder=True):
        raise ShareError(f"{point}: mount only inside your home")
    if any(layer.point == point for layer in view.layers):
        raise ShareError(f"{point}: mount point busy")
    existing = view.get(point)
    if existing is not None and not existing.is_dir:
        raise ShareError(f"{point}: not a directory")
    row = PlayerMount.objects.create(user=user, machine=view.machine, host=share_row.machine, host_path=share_row.path, account=share_row.profile,
                                     mount_path=point, secret=share_row.code, share=share_row)
    _changed()
    return row


def mounted_by(share_row):
    """Кто подключил раздачу: логины игроков."""
    return sorted(set(share_row.mounts.values_list("user__username", flat=True)))


def _changed():
    from filesystem.machine_view import MachineView

    MachineView.generation += 1


def allows(view, share_row, path, method):
    """drop: удалять и менять только своё (что игрок положил сам), класть новое — можно. Бросает NotPermitted."""
    from filesystem import rights

    if share_row.mode != Share.Mode.DROP:
        return
    user_id = getattr(view.user, "pk", None)

    def mine(entry):
        return entry.is_dir or (entry.placement is None and entry.player is not None and entry.player.changed_by_id == user_id)

    if method.startswith("put_"):
        found = view.get(path)
        if found is not None and not mine(found):
            raise rights.NotPermitted("share")
        return
    targets = view.under(path) if method == "remove" else [view.get(path)]
    if any(entry is None or not mine(entry) for entry in targets):
        raise rights.NotPermitted("share")
