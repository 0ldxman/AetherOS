"""Размер и сырые байты файла для команд терминала: с учётом ключей игрока и прогресса его сессии по слоям."""
from filesystem.rawview import build_raw
from filesystem.size import file_size
from wiki.access import player_keys


def keys_of(context):
    request = context.request
    return player_keys(request.user) if request is not None and request.user.is_authenticated else frozenset()


def _state(entry):
    return entry.session_file.state if entry.session_file else ""


def size_of(context, entry):
    return file_size(entry.machine_file, _state(entry), keys_of(context))


def raw_of(context, entry):
    return build_raw(entry.machine_file, _state(entry), keys_of(context))
