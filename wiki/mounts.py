"""Какие тома вики смонтированы на машине игрока.

None значит «без ограничений»: нет машины (служебные вызовы, тесты) или у машины не смонтирован
ни один том. Иначе словарь {id корневого неймспейса: порядок}.
"""


def mounted_roots(request):
    cached = getattr(request, "_wiki_mounts", False)
    if cached is not False:
        return cached

    mounts = None
    machine = _machine(request)

    if machine is not None:
        rows = dict(machine.volume_mounts.values_list("namespace_id", "order"))
        mounts = rows or None

    request._wiki_mounts = mounts
    return mounts


def _machine(request):
    if not hasattr(request, "session") or not hasattr(request, "user"):
        return None

    from machines.current import current_machine
    from machines.models import Machine

    try:
        return current_machine(request)
    except Machine.DoesNotExist:
        return None
