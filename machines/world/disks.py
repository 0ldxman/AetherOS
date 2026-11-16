"""Диски в сценарии: том автора («Диск», ключ — слаг) и то, что стоит в точке машины («Машина: Диск», ключ — «хост:/точка»).
Подключение и отключение меняют машину для всех, как правка автора."""
from django.core.exceptions import ValidationError
from django.db.models import Max, Q

from filesystem.names import normalize_mount


class DiskError(Exception):
    pass


def volume(key):
    """Том по слагу или названию диска; нет — None."""
    from filesystem.models import Volume

    key = str(key or "").strip()
    return Volume.objects.filter(Q(slug__iexact=key) | Q(name__iexact=key)).order_by("pk").first() if key else None


def _machine(key):
    from machines.models import Machine

    key = str(key or "").strip()
    return Machine.objects.filter(Q(hostname__iexact=key) | Q(name__iexact=key)).order_by("pk").first() if key else None


def _point(text):
    try:
        return normalize_mount(str(text or "").strip())
    except ValidationError as error:
        raise DiskError(" ".join(error.messages)) from None


def key_of(machine, point):
    return f"{machine.hostname}:{point}" if machine is not None and point else ""


def parse(key):
    """(машина, точка) из «хост:/точка»; чего нет — None."""
    host, _, point = str(key or "").strip().partition(":")
    machine = _machine(host)
    try:
        point = _point(point)
    except DiskError:
        return None
    return (machine, point) if machine is not None and point else None


def at(machine, point):
    """Что видно в точке: верхнее подключение (больший порядок) или None."""
    from machines.models import MachineMount

    return (MachineMount.objects.filter(machine=machine, mount_path=point).select_related("machine", "volume", "host", "account")
            .order_by("-order", "-id").first())


def of_machine(machine):
    """Точки машины, где что-то подключено: [«хост:/точка»], по пути."""
    points = machine.mounts.exclude(mount_path="").values_list("mount_path", flat=True).distinct()
    return [key_of(machine, point) for point in sorted(set(points))]


def where(volume):
    """Где подключён том: [«хост:/точка»]."""
    rows = volume.mounts.exclude(mount_path="").select_related("machine").order_by("machine__hostname", "mount_path")
    return list(dict.fromkeys(key_of(row.machine, row.mount_path) for row in rows))


def props(key):
    """Свойства «Машина: Диск» по ключу; нет такой точки — None."""
    from machines.models import MachineMount
    from machines.world import edits

    found = parse(key)
    if found is None:
        return None
    machine, point = found
    mount = at(machine, point)
    if mount is None:
        return None
    remote = mount.mode == MachineMount.Mode.REMOTE
    return {"value": key_of(machine, point), "machine": machine.hostname, "point": point, "type": "сетевой" if remote else "диск",
            "volume": mount.volume.slug if mount.volume_id else "", "host": mount.host.hostname if remote and mount.host_id else "",
            "path": mount.host_path if remote else ("/" + mount.volume_path.strip("/") if mount.volume_path.strip("/") else "/"),
            "account": edits.account_key(mount.account) if remote and mount.account_id else "", "exists": True}


def _changed():
    from filesystem.machine_view import MachineView

    MachineView.generation += 1


def _on_top(machine, point):
    from machines.models import MachineMount

    top = MachineMount.objects.filter(machine=machine, mount_path=point).aggregate(top=Max("order"))["top"]
    return 0 if top is None else top + 1          # точка занята — новый диск ложится сверху


def attach(machine, volume, point, folder=""):
    """Подключить том (или его папку) в точку машины. Возвращает ключ «хост:/точка»."""
    from filesystem.names import normalize_inner
    from machines.models import MachineMount

    point = _point(point)
    if not point:
        raise DiskError("не задана точка")
    if volume is None:
        raise DiskError("не выбран диск")
    MachineMount.objects.create(machine=machine, volume=volume, volume_path=normalize_inner(folder or ""), mount_path=point,
                                mode=MachineMount.Mode.LOCAL, order=_on_top(machine, point))
    _changed()
    return key_of(machine, point)


def attach_remote(machine, host, path, account, point):
    """Подключить путь другой машины по сети от имени её учётки (пусто — guest). Хост должен отдавать путь."""
    from machines.models import MachineMount
    from machines.network import connection

    point = _point(point)
    if not point:
        raise DiskError("не задана точка")
    if host is None:
        raise DiskError("не выбран хост")
    if host.pk == machine.pk:
        raise DiskError("машина не подключает сама себя")
    path = "/" + str(path or "").strip().strip("/")
    if not connection.exported(host, path):
        raise DiskError(f"{host.hostname} не отдаёт {path}: добавьте экспорт")
    if account is not None and account.machine_id != host.pk:
        raise DiskError("учётка должна быть на хосте")
    MachineMount.objects.create(machine=machine, host=host, host_path=path, account=account, mount_path=point,
                                mode=MachineMount.Mode.REMOTE, order=_on_top(machine, point))
    _changed()
    return key_of(machine, point)


def detach(machine, point="", volume=None):
    """Отключить всё в точке или этот том с машины. Возвращает сколько подключений снято."""
    rows = machine.mounts.all()
    point = _point(point)
    if point:
        rows = rows.filter(mount_path=point)
    if volume is not None:
        rows = rows.filter(volume=volume)
    if not point and volume is None:
        raise DiskError("не задано, что отключить")
    count = rows.delete()[0]
    if count:
        _changed()
    return count
