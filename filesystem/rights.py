"""Права файлов: владелец, группа, режим (640) и проверка действия записи.

Три действия: r (читать файл, смотреть папку), w (менять файл, создавать и удалять в папке), x (входить в папку). Класс получателя:
владелец, группа, остальные. Пустой режим значит «права не заданы, открыто всем». Привилегии: root проходит всегда, backup читает и
входит мимо прав, restore пишет мимо прав. Слои и ключи это отдельные проверки и идут после.

Домашняя папка другой записи этой же машины по умолчанию закрыта (владелец она, режим 700), пока автор не задал права явно.
"""
import posixpath

ACTION = {"r": 4, "w": 2, "x": 1}
HOME_LOGIN = "__login__"            # подставляется в шаблон места home, чтобы найти, где в пути логин


class Denied(Exception):
    """У записи нет прав на путь (Permission denied)."""

    def __init__(self, path):
        super().__init__(path)
        self.path = path


class NotPermitted(Exception):
    """У записи нет привилегии (Operation not permitted)."""

    def __init__(self, privilege):
        super().__init__(privilege)
        self.privilege = privilege


def permits(principal, owner, group, mode, action):
    if principal.root:
        return True
    if action in "rx" and principal.has("backup"):
        return True
    if action == "w" and principal.has("restore"):
        return True
    if not mode:
        return True
    if principal.login == owner:
        digit = mode[0]
    elif group and group in principal.groups:
        digit = mode[1]
    else:
        digit = mode[2]
    return bool(int(digit) & ACTION[action])


def rights_of(view, entry):
    """(владелец, группа, режим) записи вида: свои, иначе дом чужой записи, иначе пусто (открыто)."""
    if entry.mode:
        return entry.owner, entry.group, entry.mode
    home = view.home_owner(entry.path)
    return (home, "", "700") if home else ("", "", "")


def _ancestors(path):
    parts = [part for part in path.split("/") if part]
    return ["/" + "/".join(parts[:index]) for index in range(1, len(parts))]


def check(view, principal, path, action):
    """Бросает Denied, если записи нельзя сделать action над path. principal=None: система, проверок нет."""
    if principal is None:
        return
    path = "/" + "/".join(part for part in path.split("/") if part)
    routed = view.remote_route(path)
    if routed is not None:                       # путь на сетевом диске: права проверяет хост для учётки подключения
        host_view, host_path = routed
        if host_view is None:
            raise Denied(path)
        return check(host_view, host_view.principal, host_path, action)
    if principal.root:
        return
    for ancestor in _ancestors(path):
        found = view.get(ancestor)
        owner, group, mode = rights_of(view, found) if found is not None else (view.home_owner(ancestor), "", "700" if view.home_owner(ancestor) else "")
        if mode and not permits(principal, owner, group, mode, "x"):
            raise Denied(ancestor)
    found = view.get(path)
    if found is not None:
        owner, group, mode = rights_of(view, found)
    else:
        home = view.home_owner(path)
        owner, group, mode = (home, "", "700") if home else ("", "", "")
    if not permits(principal, owner, group, mode, action):
        raise Denied(path)


def check_parent(view, principal, path, action="w"):
    """Право на папку, где лежит (или появится) path: создать и удалить."""
    check(view, principal, posixpath.dirname("/" + path.strip("/")) or "/", action)


def symbolic(mode):
    """640 -> rw-r-----; пустой режим (открыто) -> rwxrwxrwx."""
    if not mode:
        return "rwxrwxrwx"
    return "".join(("r" if int(d) & 4 else "-") + ("w" if int(d) & 2 else "-") + ("x" if int(d) & 1 else "-") for d in mode)
