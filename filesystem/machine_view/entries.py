"""Записи вида машины: слой, запись (файл или папка) и ошибки записи."""
from dataclasses import dataclass, field
import posixpath

from filesystem.models import Placement, PlayerFile
from machines.models import MachineMount

DIR, FILE = "dir", "file"
ITEM_PREFETCH = ("item__members", "item__keys__key", "item__signatures__key")      # по запросу на всё дерево, а не на файл
DATA_LIMIT = 1024 * 1024        # самые большие собственные байты записи игрока (вырезка)


class ReadOnly(Exception):
    """В это место ничего не смонтировано: писать некуда."""


class Occupied(Exception):
    """Путь занят точкой монтирования."""


class BadName(Exception):
    """Имя нового файла не годится (filesystem.names.validate_name)."""


@dataclass(frozen=True)
class Layer:
    """Монтирование в виде машины: куда оно смонтировано и какой у него экземпляр."""

    mount: MachineMount
    instance: object            # VolumeInstance или None, пока для него нет ни одной записи игрока
    host_id: int | None
    point: str                  # «/» или «/mnt/harbor»
    prefix: str                 # папка внутри тома («» = весь том)

    @property
    def remote(self):
        """Подключение по сети: содержимое берётся из вида хоста, а не из тома."""
        return self.mount.mode == "remote"

    def machine_path(self, inner):
        """Путь внутри тома -> путь на машине или None, если он вне смонтированной папки."""
        if self.prefix:
            if inner == self.prefix:
                rel = ""
            elif inner.startswith(self.prefix + "/"):
                rel = inner[len(self.prefix) + 1:]
            else:
                return None
        else:
            rel = inner
        if not rel:
            return self.point
        return ("" if self.point == "/" else self.point) + "/" + rel

    def inner_path(self, path):
        """Путь на машине -> путь внутри тома или None, если монтирование его не покрывает."""
        if self.point == "/":
            rel = path.strip("/")
        elif path == self.point:
            rel = ""
        elif path.startswith(self.point + "/"):
            rel = path[len(self.point) + 1:]
        else:
            return None
        return "/".join(part for part in (self.prefix, rel) if part)


@dataclass
class Entry:
    """Файл или папка в виде машины."""

    path: str
    kind: str = FILE
    layer: Layer | None = None
    inner: str = ""                          # путь внутри тома слоя
    placement: Placement | None = None       # откуда пришла запись из базы
    item: object = None                      # объект (из базы или выбранный игроком)
    player: PlayerFile | None = None         # запись слоя игрока, которая меняет эту запись или создаёт её
    has_base: bool = False                   # под записью игрока лежит запись из базы (удалить = надгробие)
    gates: tuple = field(default_factory=tuple)   # условия доступа: том и папки вдоль пути
    via: object = None                       # сетевое подключение (Layer), через которое запись пришла с хоста
    text: str | None = None                  # свой текст автора без объекта: у файла-размещения или члена архива

    @property
    def name(self):
        return posixpath.basename(self.path) or "/"

    @property
    def is_dir(self):
        return self.kind == DIR

    @property
    def archive(self):
        """Файл-архив: объект с членами (pak l, pak x)."""
        return self.item is not None and bool(self.item.members.all())

    @property
    def machine(self):
        return self.layer.mount.machine if self.layer is not None else None

    @property
    def hidden(self):
        return bool(self.placement and self.placement.hidden) or self.name.startswith(".")

    @property
    def system(self):
        return bool(self.placement and self.placement.system)

    @property
    def state(self):
        """Слои защиты, заданные автором (объекта, либо размещения вместо них)."""
        if self.placement is not None:
            if self.placement.state_mode == Placement.Mode.REPLACE:
                return self.placement.state
            if self.placement.state_mode == Placement.Mode.NONE:
                return ""
        if self.item is not None:
            return self.item.state
        return self.placement.state if self.placement is not None else ""            # у файла со своим текстом слои его же

    @property
    def authored(self):
        """Файл со своим текстом автора (без объекта): размещение-файл или член архива."""
        return self.item is None and self.text is not None

    @property
    def format(self):
        """Формат файла: у объекта его, у файла без объекта по расширению имени (или пусто)."""
        if self.item is not None:
            return self.item.format
        from filesystem.content.rawview.registry import format_for_extension

        found = format_for_extension(posixpath.splitext(self.name)[1]) if posixpath.splitext(self.name)[1] else None
        return found.name if found is not None else ""

    def _right(self, name):
        """Поле прав: своё у слоя игрока, иначе у размещения."""
        return (getattr(self.player, name, "") if self.player is not None else "") or (getattr(self.placement, name, "") if self.placement is not None else "")

    @property
    def owner(self):
        return self._right("owner")

    @property
    def group(self):
        return self._right("group")

    @property
    def mode(self):
        return self._right("mode")

    @property
    def progress(self):
        """Прогресс игрока по слоям."""
        return self.player.state if self.player is not None else ""

    @property
    def access(self):
        """Условие доступа к самому файлу (объекта, либо размещения вместо него)."""
        if self.placement is not None:
            if self.placement.access_mode == Placement.Mode.REPLACE:
                return self.placement.access
            if self.placement.access_mode == Placement.Mode.NONE:
                return {}
        if self.item is not None:
            return self.item.access
        return self.placement.access if self.placement is not None else {}           # у файла со своим текстом условие его же

    @property
    def conditions(self):
        """Все условия, которые должны выполняться: том, папки вдоль пути, сам файл."""
        own = () if self.is_dir else (self.access,)
        if self.is_dir and self.placement is not None and self.placement.kind == Placement.Kind.FOLDER:
            own = (self.placement.access,)
        return tuple(condition for condition in (*self.gates, *own) if condition)

    @property
    def text_override(self):
        """Своя версия тела объекта (правка игрока) или None."""
        return self.player.content if self.player is not None and self.item is not None else None

    @property
    def own_text(self):
        """Текст файла без объекта: правка или подпись игрока, иначе свой текст автора; None, если текста нет."""
        if self.item is not None:
            return None
        if self.player is not None and self.player.content is not None:
            return self.player.content
        return self.text

    @property
    def own_data(self):
        """Байты файла игрока без объекта (вырезка) или None."""
        return bytes(self.player.data) if self.player is not None and self.player.data is not None else None

    @property
    def body(self):
        """Текст файла с учётом правки игрока."""
        if self.player is not None and self.player.content is not None:
            return self.player.content
        if self.item is not None:
            return self.item.body
        return self.text or ""


def inner_paths(placements):
    """Путь внутри тома для каждого размещения: [(путь, размещение)], мелкие пути первыми."""
    by_id = {placement.pk: placement for placement in placements}
    memo = {}

    def inner_path(placement):
        if placement.pk not in memo:
            parent = by_id.get(placement.parent_id)
            memo[placement.pk] = (inner_path(parent) + "/" if parent is not None else "") + placement.name
        return memo[placement.pk]

    return sorted(((inner_path(placement), placement) for placement in placements), key=lambda row: (row[0].count("/"), row[0]))


def _depth(point):
    return len([part for part in point.split("/") if part])


def _drop(entries, path):
    """Убрать запись и всё под ней."""
    entries.pop(path, None)
    prefix = path.rstrip("/") + "/"
    for key in [key for key in entries if key.startswith(prefix)]:
        del entries[key]
