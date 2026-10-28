"""Машина игрока для вики."""


def _machine(request):
    if not hasattr(request, "session") or not hasattr(request, "user"):
        return None

    from machines.current import current_machine
    from machines.models import Machine

    try:
        return current_machine(request)
    except Machine.DoesNotExist:
        return None
