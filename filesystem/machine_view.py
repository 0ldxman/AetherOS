"""Вид файловой системы машины для игрока: тома, смонтированные на неё, и личный слой игрока поверх.

Как собирается вид (docs/storage-spec.md, раздел 3):
  1. Монтирования машины с точкой, от мелкой к глубокой, при равной глубине по порядку.
  2. Каждый том кладёт свои размещения под точку. Новая точка закрывает всё, что лежало под ней (затенение); та же точка
     складывается стопкой (объединение): одноимённая запись верхнего слоя перекрывает нижнюю, надгробие скрывает нижний файл.
  3. Сразу после слоя к нему применяется слой игрока над его экземпляром: удаления, правки, свои файлы.

Запись (put, remove, move, copy...) идёт в слой игрока: новый файл в верхний слой, покрывающий путь, правка существующего в
слой, откуда пришла запись. База не меняется.
"""
import posixpath
from dataclasses import dataclass, field

from django.utils import timezone

from filesystem import instances
from filesystem.models import KEY_FORMAT, PlayerFile, Placement, VolumeInstance
from filesystem.names import normalize_inner
from machines.models import MachineMount

DIR, FILE = "dir", "file"
DATA_LIMIT = 1024 * 1024        # самые большие собственные байты записи игрока (вырезка)


class ReadOnly(Exception):
    """В это место ничего не смонтировано: писать некуда."""


class Occupied(Exception):
    """Путь занят точкой монтирования."""


@dataclass(frozen=True)
class Layer:
    """Монтирование в виде машины: куда оно смонтировано и какой у него экземпляр."""

    mount: MachineMount
    instance: object            # VolumeInstance или None, пока для него нет ни одной записи игрока
    host_id: int | None
    point: str                  # «/» или «/mnt/harbor»
    prefix: str                 # папка внутри тома («» = весь том)

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

    @property
    def name(self):
        return posixpath.basename(self.path) or "/"

    @property
    def is_dir(self):
        return self.kind == DIR

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
        return self.item.state if self.item is not None else ""

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
        return self.item.access if self.item is not None else {}

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
        """Текст файла игрока без объекта (подпись) или None."""
        return self.player.content if self.player is not None and self.item is None else None

    @property
    def own_data(self):
        """Байты файла игрока без объекта (вырезка) или None."""
        return bytes(self.player.data) if self.player is not None and self.player.data is not None else None

    @property
    def body(self):
        """Текст файла с учётом правки игрока."""
        if self.player is not None and self.player.content is not None:
            return self.player.content
        return self.item.body if self.item is not None else ""


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


class MachineView:
    """Вид машины для игрока (user=None: только база, без слоя игрока)."""

    def __init__(self, machine, user=None):
        self.machine = machine
        self.user = user
        self._built = None

    # ---- сборка ---------------------------------------------------------------------------------------------------

    def _layers(self):
        mounts = list(MachineMount.objects.filter(machine=self.machine).exclude(mount_path="").select_related("volume"))
        mounts.sort(key=lambda mount: (_depth(mount.mount_path), mount.order, mount.id))
        volume_ids = {mount.volume_id for mount in mounts}

        local_hosts = {}
        if any(mount.mode == "remote" for mount in mounts):
            for volume_id, machine_id in MachineMount.objects.filter(volume_id__in=volume_ids, mode="local").values_list("volume_id", "machine_id"):
                local_hosts.setdefault(volume_id, set()).add(machine_id)

        existing = {(row.volume_id, row.host_id): row for row in VolumeInstance.objects.filter(volume_id__in=volume_ids)}
        layers = []
        for mount in mounts:
            host_id = instances.host_id_of(mount, local_hosts)
            layers.append(Layer(mount, existing.get((mount.volume_id, host_id)), host_id, mount.mount_path, mount.volume_path))
        return layers

    def _build(self):
        layers = self._layers()
        volume_ids = {layer.mount.volume_id for layer in layers}
        by_volume = {}
        for placement in Placement.objects.filter(volume_id__in=volume_ids).select_related("item"):
            by_volume.setdefault(placement.volume_id, []).append(placement)

        rows = {}
        instance_ids = {layer.instance.pk for layer in layers if layer.instance is not None}
        if self.user is not None and instance_ids:
            for row in PlayerFile.objects.filter(user=self.user, instance_id__in=instance_ids).select_related("item"):
                rows.setdefault(row.instance_id, []).append(row)

        entries, points = {}, set()
        for layer in layers:
            if layer.point not in points:
                if layer.point != "/":
                    _drop(entries, layer.point)                     # новая точка закрывает то, что лежало под ней
                points.add(layer.point)
            entries.setdefault(layer.point, Entry(layer.point, DIR))
            gates_of = self._lay(entries, layer, by_volume.get(layer.mount.volume_id, []))
            if layer.instance is not None:
                self._overlay(entries, layer, rows.get(layer.instance.pk, []), gates_of)

        self._add_directories(entries)
        return entries, layers

    def _lay(self, entries, layer, placements):
        rows = inner_paths(placements)
        folders = {}
        for ipath, placement in rows:
            if placement.kind == Placement.Kind.FOLDER:
                folders[ipath] = placement.access
        gates_of = lambda ipath: (layer.mount.volume.access, *(folders.get("/".join(ipath.split("/")[:n]), {}) for n in range(1, ipath.count("/") + 1)))

        for ipath, placement in rows:                              # сначала надгробия: они скрывают только нижние слои
            if placement.kind == Placement.Kind.WHITEOUT:
                machine_path = layer.machine_path(ipath)
                if machine_path is not None and machine_path != layer.point:
                    _drop(entries, machine_path)
        for ipath, placement in rows:
            if placement.kind == Placement.Kind.WHITEOUT:
                continue
            machine_path = layer.machine_path(ipath)
            if machine_path is None or machine_path == layer.point:
                continue
            if placement.kind == Placement.Kind.FOLDER:
                entries[machine_path] = Entry(machine_path, DIR, layer, ipath, placement, None, None, True, gates_of(ipath))
            else:
                if machine_path in entries and entries[machine_path].is_dir:
                    _drop(entries, machine_path)
                entries[machine_path] = Entry(machine_path, FILE, layer, ipath, placement, placement.item, None, True, gates_of(ipath))
        return gates_of

    def _overlay(self, entries, layer, rows, gates_of):
        for row in sorted(rows, key=lambda row: (row.path.count("/"), row.path)):
            machine_path = layer.machine_path(row.path)
            if machine_path is None or machine_path == layer.point:
                continue
            base = entries.get(machine_path)
            if row.deleted_at is not None:
                _drop(entries, machine_path)
            elif row.item_id is not None:
                keeps_base = base is not None and base.item is not None and base.item.pk == row.item_id and base.layer == layer
                entries[machine_path] = Entry(
                    machine_path, FILE, layer, row.path,
                    base.placement if keeps_base else None, row.item, row,
                    bool(base is not None and base.layer == layer and base.has_base), gates_of(row.path),
                )
            elif row.content is not None or row.data is not None:
                entries[machine_path] = Entry(
                    machine_path, FILE, layer, row.path, None, None, row,
                    bool(base is not None and base.layer == layer and base.has_base), gates_of(row.path),
                )
            elif base is not None and base.layer == layer:
                base.player = row                                    # только прогресс по слоям

    @staticmethod
    def _add_directories(entries):
        for path in list(entries):
            parent = posixpath.dirname(path)
            while parent and parent != "/" and parent not in entries:
                entries[parent] = Entry(parent, DIR)
                parent = posixpath.dirname(parent)
        entries.setdefault("/", Entry("/", DIR))

    @property
    def entries(self):
        if self._built is None:
            self._built = self._build()
        return self._built[0]

    @property
    def layers(self):
        self.entries
        return self._built[1]

    def invalidate(self):
        self._built = None

    def layer_paths(self, layer):
        """Пути на машине, которые слой занимает своими размещениями (без слоя игрока и без надгробий): {путь: размещение}."""
        return self._paths_where(layer, lambda placement: placement.kind != Placement.Kind.WHITEOUT)

    def layer_paths_of_kind(self, layer, kind):
        return self._paths_where(layer, lambda placement: placement.kind == kind)

    def _paths_where(self, layer, keep):
        placements = list(Placement.objects.filter(volume_id=layer.mount.volume_id).select_related("item"))
        found = {}
        for ipath, placement in inner_paths(placements):
            machine_path = layer.machine_path(ipath)
            if machine_path is not None and machine_path != layer.point and keep(placement):
                found[machine_path] = placement
        return found

    # ---- чтение ---------------------------------------------------------------------------------------------------

    def get(self, path):
        return self.entries.get(self._clean(path))

    def exists(self, path):
        return self.get(path) is not None

    def is_directory(self, path):
        found = self.get(path)
        return found is not None and found.is_dir

    def children(self, path):
        """Записи прямо под папкой, папки первыми, затем по имени без учёта регистра."""
        path = self._clean(path)
        prefix = path.rstrip("/") + "/"
        found = [
            entry for key, entry in self.entries.items()
            if key != path and key.startswith(prefix) and "/" not in key[len(prefix):]
        ]
        return sorted(found, key=lambda entry: (not entry.is_dir, entry.name.casefold()))

    def under(self, path):
        """Сама запись и всё под ней (для рекурсивных операций), мелкое первым."""
        path = self._clean(path)
        prefix = path.rstrip("/") + "/"
        found = [entry for key, entry in self.entries.items() if key == path or key.startswith(prefix)]
        return sorted(found, key=lambda entry: (entry.path.count("/"), entry.path))

    def held_keys(self, path):
        """Слаги ключей, лежащих в папке path (папка ключей записи, откуда бы ни пришёл файл: в том числе с удалённого тома)."""
        return {
            entry.item.slug for entry in self.children(path)
            if not entry.is_dir and entry.item is not None and entry.item.format == KEY_FORMAT
        }

    @staticmethod
    def _clean(path):
        return "/" + normalize_inner(path)

    # ---- запись в слой игрока -------------------------------------------------------------------------------------

    def _target(self, path):
        """Слой, куда ляжет новое по этому пути: верхний из покрывающих его монтирований."""
        path = self._clean(path)
        if path in {layer.point for layer in self.layers}:
            raise Occupied(path)
        for layer in reversed(self.layers):
            inner = layer.inner_path(path)
            if inner:
                return layer, inner
        raise ReadOnly(path)

    def _row(self, layer, inner):
        instance = layer.instance or instances.get_or_create(layer.mount.volume_id, layer.host_id)
        row, _ = PlayerFile.objects.get_or_create(user=self.user, instance=instance, path=inner)
        return row

    def _save(self, row, **fields):
        for name, value in fields.items():
            setattr(row, name, value)
        row.save()
        self.invalidate()
        return row

    def _clear(self, **fields):
        return {"deleted_at": None, "origin_path": "", "trashed_at": None, "purge_at": None, **fields}

    def put_item(self, path, item, state="", content=None):
        """Положить ссылку на объект (cp, mv, распаковка, вложение письма, ключ в папку секретов)."""
        layer, inner = self._target(path)
        return self._save(self._row(layer, inner), **self._clear(item=item, content=content, data=None, state=state))

    def put_text(self, path, text, state=""):
        """Файл игрока без объекта с текстом (подпись)."""
        layer, inner = self._target(path)
        return self._save(self._row(layer, inner), **self._clear(item=None, content=text, data=None, state=state))

    def put_data(self, path, data, state=""):
        """Файл игрока без объекта с байтами (вырезка)."""
        if len(data) > DATA_LIMIT:
            raise ValueError("too large")
        layer, inner = self._target(path)
        return self._save(self._row(layer, inner), **self._clear(item=None, content=None, data=bytes(data), state=state))

    def edit_text(self, path, text):
        """Своя версия текста существующего файла."""
        found = self.get(path)
        if found is None or found.is_dir:
            raise FileNotFoundError(path)
        row = self._row(found.layer, found.inner)
        fields = {"content": text, "data": None, "deleted_at": None}
        if found.item is not None:
            fields["item"] = found.item                                   # правка тела объекта: ссылка остаётся
        return self._save(row, **fields)

    def set_progress(self, path, state):
        """Прогресс игрока по слоям файла."""
        found = self.get(path)
        if found is None or found.is_dir:
            raise FileNotFoundError(path)
        row = found.player or self._row(found.layer, found.inner)
        return self._save(row, state=state)

    def remove(self, path):
        """Удалить файл или папку со всем внутри. Возвращает число удалённых файлов."""
        count = 0
        for found in reversed(self.under(path)):
            if found.layer is None:
                continue
            count += not found.is_dir
            for _ in range(3):                                              # файл нижнего слоя мог просвечивать сквозь удалённый
                self._delete_one(found)
                self.invalidate()
                found = self.get(found.path)
                if found is None or found.is_dir or found.layer is None:
                    break
        self.invalidate()
        return count

    def _delete_one(self, found):
        row = found.player
        if row is not None and not found.has_base:
            row.delete()                                                    # файл игрока: следа не остаётся
        else:
            self._save(self._row(found.layer, found.inner), deleted_at=timezone.now(), item=None, content=None, data=None, state="")

    def copy(self, source, target):
        """Скопировать файл или папку: те же объекты и прогресс, свои копии записей. Возвращает число файлов."""
        count = 0
        base = self._clean(source)
        for found in self.under(source):
            if found.is_dir:
                continue
            destination = self._clean(target + found.path[len(base):])
            self._put_like(destination, found)
            count += 1
        return count

    def move(self, source, target):
        count = self.copy(source, target)
        if self._clean(target) != self._clean(source):
            self.remove(source)
        return count

    def _put_like(self, path, found):
        if found.item is not None:
            self.put_item(path, found.item, found.progress, found.text_override)
        elif found.own_data is not None:
            self.put_data(path, found.own_data, found.progress)
        else:
            self.put_text(path, found.own_text or "", found.progress)
