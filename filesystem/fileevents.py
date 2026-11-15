"""События файлов игрока, которые делает команда, а не вид машины: перенос, копия, новый файл, очистка корзины.

Вид машины (machine_view) переносит и копирует и для почты, и для корзины, поэтому события шлют сами команды через эти обёртки.
"""


def _send(view, name, **data):
    if view.user is None:
        return
    from engine.events import emit

    emit(name, view.user, machine=view.machine, login=view.login or "", **data)


def _slug(entry):
    return entry.item.slug if entry is not None and entry.item is not None else ""


def _files(view, path):
    return [(entry.path, _slug(entry)) for entry in view.under(path) if not entry.is_dir]


def moved(view, old, new, item=""):
    """Файл переехал: file.moved (путь — новый, from — прежний)."""
    if old != new:
        _send(view, "file.moved", path=new, item=item, **{"from": old})


def move(view, source, target):
    """view.move и file.moved на каждый перенесённый файл. Возвращает число файлов."""
    base, files = view._clean(source), _files(view, source)
    count = view.move(source, target)
    dest = view._clean(target)
    for path, item in files:
        moved(view, path, dest + path[len(base):], item)
    return count


def copy(view, source, target):
    """view.copy и file.created (via copied, from — источник) на каждый новый файл."""
    base, files = view._clean(source), _files(view, source)
    count = view.copy(source, target)
    dest = view._clean(target)
    for path, item in files:
        _send(view, "file.created", path=dest + path[len(base):], item=item, via="copied", **{"from": path})
    return count


def created(view, path):
    """Игрок сделал новый файл (вырезка, подпись, текст из архива)."""
    _send(view, "file.created", path=path, item=_slug(view.get(path)), via="created")


def purged(view, path, item=""):
    """Файл стёрт из корзины насовсем; path — его место в корзине."""
    _send(view, "file.purged", path=path, item=item)
