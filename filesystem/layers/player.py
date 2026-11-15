"""Слои файла у игрока: все слои со снятыми, устойчивые номера и то, что с ними делает сценарий.

Номер слоя не меняется, когда сверху снимают или добавляют другие: слой из описания — «c<номер в описании>» (c1 — верхний),
добавленный поверх (damaged после корзины, слой от сценария) — «a<номер добавления>» (a1 — самый ранний). Снятый добавленный слой
пропадает, снятый слой описания остаётся в списке со «снят».
"""
from dataclasses import dataclass

from filesystem.layers.compiler import compile_text
from filesystem.layers.registry import registry
from filesystem.layers.stack import load_progress


class LayerError(Exception):
    pass


@dataclass
class LayerInfo:
    id: str                      # c2, a1
    type: str                    # encrypted, binary…
    index: int                   # место в списке, 1 — верхний
    removed: bool
    attempts_left: int | None    # None — без ограничения
    added: bool                  # добавлен поверх описания (игроку, сценарием, событием)


def _canonical(text):
    return compile_text(text) if (text or "").strip() else []


def listing(canonical_text, raw_state):
    """Все слои файла, верхний первым: добавленные, потом слои описания (снятые — со «снят»)."""
    canonical, progress = _canonical(canonical_text), load_progress(raw_state or "", canonical_text or "")
    out = []
    for j, item in enumerate(progress.added):
        cls = registry.get(item.name)
        limit = cls.max_attempts(item.params) if cls is not None else None
        out.append(LayerInfo(f"a{len(progress.added) - j}", item.name, 0, False,
                             None if limit is None else max(limit - item.attempts, 0), True))
    for i, layer in enumerate(canonical):
        limit = layer.state.max_attempts(layer.params)
        used = progress.attempts.get(str(i), 0)
        out.append(LayerInfo(f"c{i + 1}", layer.state.name, 0, i < progress.removed, None if limit is None else max(limit - used, 0), False))
    for n, info in enumerate(out, 1):
        info.index = n
    return out


def top_id(canonical_text, raw_state):
    """Номер верхнего неснятого слоя (пусто — слоёв нет)."""
    return next((info.id for info in listing(canonical_text, raw_state) if not info.removed), "")


def left(canonical_text, raw_state):
    return sum(1 for info in listing(canonical_text, raw_state) if not info.removed)


def _entry(view, path):
    entry = view.get(path)
    if entry is None or entry.is_dir:
        raise LayerError(f"нет файла {path}")
    return entry


def of(view, path):
    entry = _entry(view, path)
    return listing(entry.state, entry.progress)


def _emit(view, name, **data):
    from engine.events import emit

    if view.user is not None:
        emit(name, view.user, machine=view.machine, login=view.login or "", **data)


def _slug(entry):
    return entry.item.slug if entry.item is not None else ""


def remove(view, path, layer_id="", quiet=False):
    """Снять слой layer_id (пусто — верхний) и всё, что над ним. quiet — без хуков (событие «снят» всё равно).
    Возвращает (путь файла после хуков, [снятые номера])."""
    layers = [info for info in of(view, path) if not info.removed]
    if not layers:
        raise LayerError(f"у {path} нет слоёв")
    wanted = layer_id or layers[0].id
    ids = [info.id for info in layers]
    if wanted not in ids:
        raise LayerError(f"у {path} нет слоя {wanted} (или он уже снят)")
    done = []
    for info in layers[:ids.index(wanted) + 1]:
        if quiet:
            entry = _entry(view, path)
            progress = load_progress(entry.progress, entry.state)
            if progress.added:
                progress.added.pop(0)
            else:
                progress.attempts.pop(str(progress.removed), None)
                progress.removed += 1
            view.set_progress(path, progress.dump())
            _emit(view, "layer.removed", path=path, item=_slug(entry), layer=info.type, id=info.id, left=left(entry.state, progress.dump()),
                  wrong=[], given="")
        else:
            from filesystem.layers.unlock import unlock_file

            outcome = unlock_file(view, path, None, force=True)
            path = outcome.path or path
        done.append(info.id)
    return path, done


def add(view, path, layer_type, args=""):
    """Положить слой поверх (как в описании: «> тип аргументы»). Возвращает его номер."""
    entry = _entry(view, path)
    try:
        compiled = compile_text(f"> {layer_type} {args}".rstrip())
    except Exception as error:                     # noqa: BLE001 — текст ошибки описания слоя
        raise LayerError(f"слой «{layer_type} {args}»: {error}") from error
    if len(compiled) != 1:
        raise LayerError(f"слой «{layer_type}» не разобрался")
    progress = load_progress(entry.progress, entry.state)
    progress.push(compiled[0].state.name, compiled[0].params)
    view.set_progress(path, progress.dump())
    number = f"a{len(progress.added)}"
    _emit(view, "layer.added", path=path, item=_slug(entry), layer=compiled[0].state.name, id=number, left=left(entry.state, progress.dump()))
    return number


def added(view, path, count):
    """События «добавлен» для последних count слоёв, положенных поверх (damaged после корзины)."""
    entry = _entry(view, path)
    progress = load_progress(entry.progress, entry.state)
    for j in range(min(count, len(progress.added))):
        _emit(view, "layer.added", path=path, item=_slug(entry), layer=progress.added[j].name, id=f"a{len(progress.added) - j}",
              left=left(entry.state, entry.progress))


def reset(view, path):
    """Вернуть все слои, как в описании (добавленные пропадают, снятые возвращаются, попытки с нуля)."""
    _entry(view, path)
    view.set_progress(path, "")


def reset_attempts(view, path, layer_id=""):
    """Попытки слоя (пусто — верхнего) с нуля."""
    entry = _entry(view, path)
    progress = load_progress(entry.progress, entry.state)
    wanted = layer_id or top_id(entry.state, entry.progress)
    if wanted.startswith("a") and wanted[1:].isdigit() and 1 <= int(wanted[1:]) <= len(progress.added):
        progress.added[len(progress.added) - int(wanted[1:])].attempts = 0
    elif wanted.startswith("c") and wanted[1:].isdigit():
        progress.attempts.pop(str(int(wanted[1:]) - 1), None)
    else:
        raise LayerError(f"у {path} нет слоя {wanted or '?'}")
    view.set_progress(path, progress.dump())
