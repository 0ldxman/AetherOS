"""Подключение к хосту: хост, путь на нём и запись хоста, под которой идёт работа.

Подключение даёт вид машины-хоста от имени записи: её группы, привилегии и права файлов хоста. Подключиться можно только к пути,
который хост отдаёт (machines.models.Export), и клиент видит только его поддерево. Если на хосте самом есть сетевые монтирования внутри
отдаваемого пути, их содержимое доступно клиенту по учётке монтирования хоста (цепочка); циклов нет: машина, уже стоящая в цепочке,
второй раз не подключается.
"""
import posixpath

from machines.groups import principal_for
from machines.models import Export

MAX_CHAIN = 6


def exported(host, path):
    """Отдаёт ли хост этот путь: он сам или то, что лежит под одним из экспортов."""
    path = "/" + path.strip("/")
    for export in Export.objects.filter(machine=host).values_list("path", flat=True):
        base = export.rstrip("/")
        if base == "" or path == base or path.startswith(base + "/"):
            return True
    return False


def account_of(host, login):
    """Запись хоста по логину (первая по частоте) или None."""
    return host.profiles.filter(login=login).order_by("freq").first() if login else None


def connect(client, host, host_path, account, user, trail=frozenset()):
    """Вид хоста для подключения или None, если подключиться нельзя (цепочка длинная или замкнулась, пути нет в экспорте, нет учётки)."""
    from filesystem.machine_view import MachineView

    chain = trail | {client.pk}
    if host.pk in chain or len(chain) > MAX_CHAIN or not exported(host, host_path):
        return None
    account = account or account_of(host, "guest")
    if account is None or account.machine_id != host.pk:
        return None
    return MachineView(host, user, principal_for(account), trail=chain)


def parent_of(path):
    return posixpath.dirname(path.rstrip("/")) or "/"
