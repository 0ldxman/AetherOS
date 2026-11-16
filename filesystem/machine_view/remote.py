"""Сетевые подключения: куда ведёт путь и как операция идёт на хост."""
from filesystem.machine_view.entries import ReadOnly


class RemoteMixin:
    def remote_route(self, path):
        """(вид хоста, путь на хосте) для пути, который лежит в сетевом подключении, или None. Вид хоста None: подключение оборвано."""
        path = self._clean(path)
        for layer in reversed(self.layers):
            inner = layer.inner_path(path)
            if inner is None:
                continue
            if not layer.remote:
                return None
            base = layer.mount.host_path.rstrip("/")
            return self._host_view(layer), (base + "/" + inner if inner else base) or "/"
        return None

    def read_only_at(self, path):
        """Путь лежит на диске, подключённом «только чтение» (верхнее монтирование, которое его покрывает)?"""
        path = self._clean(path)
        for layer in reversed(self.layers):
            if layer.inner_path(path) is not None:
                return bool(getattr(layer.mount, "read_only", False))
        return False

    def _delegate(self, path, method, *args, **kwargs):
        """Операция над путём в сетевом подключении выполняется на хосте от имени учётки подключения. (True, итог) или (False, None)."""
        routed = self.remote_route(path)
        if routed is None:
            return False, None
        view, host_path = routed
        if view is None or (self.principal is not None and self.read_only_at(path)):
            raise ReadOnly(path)                 # оборвано или подключено «только чтение»: запись не идёт на хост
        try:
            return True, getattr(view, method)(host_path, *args, **kwargs)
        finally:
            self.invalidate()
