"""Ключи игрока: файлы в его папке секретов (место secrets его записи на машине, machines/places.py).

Ключ это объект формата key. Ключ, извлечённый из байтов файла (kex), появляется в вид машины файлом secrets/<слаг>. Ключи игрока на
машине это ключи, лежащие в его папке секретов, откуда бы они туда ни попали (в том числе из смонтированного удалённого тома):
удалил файл или отмонтировал том, потерял ключ. Имя файла и ключ это разное: ключ задаёт объект, на который файл указывает.
"""
from machines import places


def secrets_dir(machine, login):
    """Папка секретов записи на машине (канонический путь) или None."""
    return places.resolve(machine, "secrets", login)


def _view(session):
    from filesystem.machine_view import MachineView

    return MachineView(session.profile.machine, session.user)


def slugs_of(session):
    """Слаги ключей в папке секретов записи этой сессии."""
    if session is None:
        return frozenset()
    folder = secrets_dir(session.profile.machine, session.profile.login)
    return frozenset(_view(session).held_keys(folder)) if folder else frozenset()


def held(view, machine, login):
    """Ключи в папке секретов: список (имя файла, слаг)."""
    from filesystem.models import KEY_FORMAT

    folder = secrets_dir(machine, login)
    if not folder:
        return []
    return sorted(
        (entry.name, entry.item.slug) for entry in view.children(folder)
        if not entry.is_dir and entry.item is not None and entry.item.format == KEY_FORMAT
    )


def put(view, machine, login, item):
    """Положить ключ в папку секретов записи ссылкой на его объект. Возвращает (путь, создан ли заново)."""
    folder = secrets_dir(machine, login)
    path = f"{folder}/{item.slug}"
    found = view.get(path)
    if found is not None and found.item is not None and found.item.pk == item.pk:
        return path, False
    view.put_item(path, item)
    return path, True
