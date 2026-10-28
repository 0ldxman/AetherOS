"""Файловая система машины так, как её видит игрок: вид из монтирований и слой игрока (filesystem/machine_view.py)."""
from pathlib import PurePosixPath


class VirtualFilesystem:
    def __init__(self, context):
        self.context = context
        self._entries_cache = None

    def _entries(self):
        """Все записи вида: путь -> Entry. Считается один раз на команду."""
        if self._entries_cache is None:
            self._entries_cache = self.context.view.entries
        return self._entries_cache

    def get_file(self, path):
        return self._entries().get(path)

    def exists(self, path):
        return path == "/" or path in self._entries()

    def is_directory(self, path):
        if path == "/":
            return True
        found = self.get_file(path)
        return found is not None and found.is_dir

    def children(self, path):
        """Записи прямо под папкой (папки первыми, затем по имени)."""
        return self.context.view.children(path)

    def list_directory(self, path):
        if not self.is_directory(path):
            raise NotADirectoryError(path)
        return [{"name": entry.name, "is_directory": entry.is_dir, "hidden": entry.hidden} for entry in self.children(path)]

    def parent_path(self, path):
        return str(PurePosixPath(path).parent)
