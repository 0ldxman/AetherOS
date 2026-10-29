"""Сборка вида машины: монтирования -> слои -> записи, слой игрока поверх."""
from dataclasses import replace
import posixpath

from filesystem.machine_view.entries import DIR, Entry, FILE, ITEM_PREFETCH, Layer, _depth, _drop, inner_paths
from filesystem.models import Placement, PlayerFile, VolumeInstance
from machines.models import MachineMount


class BuildMixin:
    def _layers(self):
        mounts = list(MachineMount.objects.filter(machine=self.machine).exclude(mount_path="").select_related("volume", "host", "account"))
        mounts += self._player_mounts()
        mounts.sort(key=lambda mount: (_depth(mount.mount_path), mount.order, mount.id))
        volume_ids = {mount.volume_id for mount in mounts if mount.mode == "local"}
        existing = {row.volume_id: row for row in VolumeInstance.objects.filter(volume_id__in=volume_ids, host=self.machine)}
        layers = []
        for mount in mounts:
            if mount.mode == "remote":
                layers.append(Layer(mount, None, mount.host_id, mount.mount_path, ""))
            else:
                layers.append(Layer(mount, existing.get(mount.volume_id), mount.machine_id, mount.mount_path, mount.volume_path))
        return layers

    def _player_mounts(self):
        """Диски, которые игрок подключил сам (mnt): пока учётка хоста не сменила пароль, после этого диск пропал."""
        if self.user is None:
            return []
        from machines.models import PlayerMount

        found = []
        for row in PlayerMount.objects.filter(machine=self.machine, user=self.user).select_related("host", "account"):
            if row.account.password_hash != row.secret:
                continue
            mount = row.as_mount()
            mount.host, mount.account = row.host, row.account
            found.append(mount)
        return found

    def _build(self):
        layers = self._layers()
        volume_ids = {layer.mount.volume_id for layer in layers if not layer.remote}
        by_volume = {}
        for placement in Placement.objects.filter(volume_id__in=volume_ids).select_related("item").prefetch_related(*ITEM_PREFETCH):
            by_volume.setdefault(placement.volume_id, []).append(placement)

        rows = {}
        instance_ids = {layer.instance.pk for layer in layers if layer.instance is not None}
        if self.user is not None and instance_ids:
            for row in PlayerFile.objects.filter(user=self.user, instance_id__in=instance_ids).select_related("item").prefetch_related(*ITEM_PREFETCH):
                rows.setdefault(row.instance_id, []).append(row)

        entries, points = {}, set()
        for layer in layers:
            if layer.point not in points:
                if layer.point != "/":
                    _drop(entries, layer.point)                     # новая точка закрывает то, что лежало под ней
                points.add(layer.point)
            entries.setdefault(layer.point, Entry(layer.point, DIR, gates=() if layer.remote or not layer.mount.volume.access else (layer.mount.volume.access,)))
            if layer.remote:
                self._lay_remote(entries, layer)
                continue
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

    def _host_view(self, layer):
        """Вид хоста для сетевого подключения или None (нельзя подключиться): один на сборку."""
        key = layer.mount.pk
        hosts = self._cache().setdefault("hosts", {})
        if key not in hosts:
            from machines import connection

            mount = layer.mount
            hosts[key] = None if mount.host_id is None else connection.connect(self.machine, mount.host, mount.host_path, mount.account, self.user, self.trail)
        return hosts[key]

    def _lay_remote(self, entries, layer):
        """Поддерево хоста ложится под точку подключения: записи те же, что видит на хосте учётка подключения."""
        view = self._host_view(layer)
        if view is None:
            return
        base = layer.mount.host_path.rstrip("/")
        shift = layer.point.rstrip("/")
        for found in view.under(base or "/"):
            rest = found.path[len(base):]
            if not rest and not found.is_dir:
                continue                                    # подключается папка, а не файл
            path = (shift + rest) or "/"
            entries[path] = replace(found, path=path, via=layer)

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
        state = self._cache()
        if "built" not in state:
            state["built"] = self._build()
        return state["built"][0]

    @property
    def layers(self):
        self.entries
        return self._state["built"][1]

    def invalidate(self):
        type(self).generation += 1
        self._state.clear()

    def layer_paths(self, layer):
        """Пути на машине, которые слой занимает своими размещениями (без слоя игрока и без надгробий): {путь: размещение}."""
        return self._paths_where(layer, lambda placement: placement.kind != Placement.Kind.WHITEOUT)

    def layer_paths_of_kind(self, layer, kind):
        return self._paths_where(layer, lambda placement: placement.kind == kind)

    def _paths_where(self, layer, keep):
        if layer.remote:
            return {}
        placements = list(Placement.objects.filter(volume_id=layer.mount.volume_id).select_related("item"))
        found = {}
        for ipath, placement in inner_paths(placements):
            machine_path = layer.machine_path(ipath)
            if machine_path is not None and machine_path != layer.point and keep(placement):
                found[machine_path] = placement
        return found
