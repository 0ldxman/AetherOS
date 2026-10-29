"""Размер и сырые байты файла для команд терминала: с учётом ключей игрока и прогресса его сессии по слоям."""
from filesystem.machine_view import MachineView
from filesystem.content.rawview import build_raw
from filesystem.content.size import file_size
from secure.requestkeys import request_keys


def keys_of(context):
    """Ключи игрока: считаются один раз на команду и заново только после записи (ключ мог появиться)."""
    stamp = MachineView.generation
    found = getattr(context, "_keys", None)
    if found is None or found[0] != stamp:
        request = context.request
        found = (stamp, request_keys(request) if request is not None and request.user.is_authenticated else frozenset())
        context._keys = found
    return found[1]


def viewer_of(context):
    """Почтовый читатель игрока (для писем в байтах файла) или None; один на команду."""
    if not hasattr(context, "_viewer"):
        context._viewer = _viewer(context.request)
    return context._viewer


def _viewer(request):
    if request is None:
        return None
    try:
        from mail.access import viewer_for

        return viewer_for(request)
    except Exception:
        return None


def size_of(context, entry):
    return file_size(entry, context.view, keys_of(context), viewer_of(context))


def raw_of(context, entry):
    context.require(entry.path, "r")
    return build_raw(entry, context.view, keys_of(context), viewer=viewer_of(context))
