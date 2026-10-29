"""Чтение собранного вида: пути, папки, ключи, дом чужой записи."""
from filesystem import rights
from filesystem.models import KEY_FORMAT
from filesystem.names import normalize_inner


class ReadMixin:
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

    def home_owner(self, path):
        """Логин записи этой машины, чья домашняя папка содержит path, или None."""
        homes = self._cache()
        if "homes" not in homes:
            from machines import places

            template = places.resolve(self.machine, "home", rights.HOME_LOGIN)
            prefix, _, suffix = (template or "").partition(rights.HOME_LOGIN)
            logins = set(self.machine.profiles.values_list("login", flat=True)) if template else set()
            homes["homes"] = (prefix, suffix, logins)
        prefix, suffix, logins = homes["homes"]
        if not logins or not path.startswith(prefix):
            return None
        login = path[len(prefix):].split("/")[0]
        if login not in logins:
            return None
        base = prefix + login + suffix
        return login if path == base or path.startswith(base + "/") else None
