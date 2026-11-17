"""Что сценарий делает с файлом игрока (размещением): положить объект, создать свой файл, перенести, подменить объект,
удалить в корзину или насовсем, вернуть из корзины.

Размещение — игрок, машина, путь. Работает в виде машины игрока (первая его учётка на машине); шлёт те же события, что и команды
игрока (file.moved, file.deleted, …), поэтому ждущие ноды идут за файлом. Ошибка — PlacementError с текстом для журнала.
"""
import posixpath


class PlacementError(Exception):
    pass


def _view(user, machine):
    from filesystem.copies import accounts
    from filesystem.machine_view import view_for

    logins = [login for _, login in accounts(user, machine)]
    return view_for(machine, user, login=logins[0] if logins else None), (logins[0] if logins else "")


def _path(path):
    path = posixpath.normpath(str(path or "").strip())
    if not path.startswith("/"):
        raise PlacementError("путь должен начинаться с «/»")
    return path


def _existing(view, path):
    found = view.get(path)
    if found is None or found.is_dir:
        raise PlacementError(f"нет файла {path}")
    return found


def _slug(entry):
    return entry.item.slug if entry is not None and entry.item is not None else ""


def trash_dir(machine, login):
    from machines.world import places

    return places.resolve(machine, "trash", login) or "/trash"


def fill(path, login):
    from mail import letters

    return letters.fill(str(path or ""), {"login": login})


def add(user, machine, path, item):
    """Положить объект по пути. Ключ без пути — в папку секретов учётки. Возвращает путь."""
    from filesystem import arrivals, keystore
    from filesystem.models import KEY_FORMAT

    view, login = _view(user, machine)
    if not str(path or "").strip() and item.format_id == KEY_FORMAT:
        if not keystore.secrets_dir(machine, login):
            raise PlacementError(f"у учётки {login or '?'} нет папки секретов")
        found, _ = keystore.put(view, machine, login, item, source="scenario")
        return found
    path = _path(fill(path, login))
    view.put_item(path, item)
    arrivals.got(view, path, item, "scenario")
    return path


def create(user, machine, path, text):
    """Свой файл игрока с текстом (без объекта). Возвращает путь."""
    from filesystem import fileevents

    view, login = _view(user, machine)
    path = _path(fill(path, login))
    if view.exists(path):
        raise PlacementError(f"{path} уже есть")
    view.put_text(path, str(text or ""))
    fileevents.created(view, path)
    return path


def move(user, machine, path, target):
    from filesystem import fileevents

    view, login = _view(user, machine)
    _existing(view, path)
    target = _path(fill(target, login))
    if not target or target == path:
        return path
    if view.exists(target):
        raise PlacementError(f"{target} занят")
    fileevents.move(view, path, target)
    return target


def replace(user, machine, path, item):
    """Подменить объект в файле: путь и прогресс игрока по слоям — новые (как у нового файла)."""
    from engine.events import emit

    view, login = _view(user, machine)
    _existing(view, path)
    view.remove(path)
    view.put_item(path, item)
    emit("file.changed", user, machine=machine, login=login, path=path, item=item.slug)
    return path


def trash(user, machine, path):
    """В корзину, как del у игрока. Возвращает путь в корзине."""
    from engine.events import emit
    from filesystem.trash import in_trash, to_trash

    view, login = _view(user, machine)
    found = _existing(view, path)
    folder = trash_dir(machine, login)
    if in_trash(path, folder):
        return path
    moved = to_trash(view, folder, path)
    target = moved[0][0] if moved else path
    emit("file.deleted", user, machine=machine, login=login, path=path, to=target, item=_slug(found))
    return target


def purge(user, machine, path):
    """Удалить насовсем: без следа и без корзины. Возвращает пустой путь."""
    from filesystem import fileevents

    view, _ = _view(user, machine)
    found = _existing(view, path)
    view.remove(path)
    fileevents.purged(view, path, _slug(found))
    return ""


def restore(user, machine, path, target=""):
    """Вернуть из корзины на прежнее место (или по пути target). Возвращает новый путь."""
    from engine.events import emit

    view, login = _view(user, machine)
    found = _existing(view, path)
    origin = found.player.origin_path if found.player is not None and found.player.trashed_at is not None else ""
    if not origin:
        raise PlacementError(f"{path} не в корзине")
    target = _path(fill(target, login)) if str(target or "").strip() else origin
    if view.exists(target):
        raise PlacementError(f"{target} занят")
    view.move(path, target)
    emit("file.restored", user, machine=machine, login=login, path=target, item=_slug(found), **{"from": path})
    return target
