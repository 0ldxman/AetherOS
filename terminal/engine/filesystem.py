from dataclasses import dataclass
from pathlib import PurePosixPath

from filesystem.models import MachineFile, SessionFile


@dataclass(frozen=True)
class Entry:
    """Файл так, как его видит игрок в своей сессии.

    path -- путь в сессии (после rename или для копии он может отличаться
    от machine_file.path), session_file -- запись сессии или None, если
    сессия файл не трогала."""

    path: str
    file_type: str
    machine_file: MachineFile
    session_file: SessionFile | None = None


class VirtualFilesystem:
    def __init__(self, context):
        self.context = context
        self._entries_cache: dict[str, Entry] | None = None

    def _entries(self) -> dict[str, Entry]:
        """Все файлы сессии: путь -> Entry. Считается один раз на команду.

        1. Файл машины, к которому у сессии нет записей, виден как есть.
        2. Если записи есть, файл виден только там, где её путь указывает
           (rename сдвигает, copy добавляет копию).
        3. Запись с deleted_at (надгробие) файл прячет."""
        if self._entries_cache is None:
            machine_files = MachineFile.objects.filter(
                machine=self.context.machine,
            )
            rows = list(
                SessionFile.objects.filter(
                    session=self.context.session,
                ).select_related("file")
            )
            touched = {row.file_id for row in rows}
            entries: dict[str, Entry] = {}

            for machine_file in machine_files:
                if machine_file.id not in touched:
                    entries[machine_file.path] = Entry(
                        machine_file.path,
                        machine_file.file_type,
                        machine_file,
                    )

            for row in rows:
                if row.deleted_at is None:
                    entries[row.path] = Entry(
                        row.path,
                        row.file.file_type,
                        row.file,
                        row,
                    )

            self._entries_cache = entries

        return self._entries_cache

    def get_file(self, path: str) -> Entry | None:
        return self._entries().get(path)

    def _has_children(self, path: str) -> bool:
        prefix = path.rstrip("/") + "/"

        return any(
            entry_path.startswith(prefix) for entry_path in self._entries()
        )

    def exists(self, path: str) -> bool:
        if path == "/":
            return True

        if self.get_file(path) is not None:
            return True

        return self._has_children(path)

    def is_directory(self, path: str) -> bool:
        if path == "/":
            return True

        file = self.get_file(path)

        if file is not None:
            return file.file_type == MachineFile.FileType.DIRECTORY

        return self._has_children(path)

    def list_directory(self, path: str) -> list[dict]:
        if not self.is_directory(path):
            raise NotADirectoryError(path)

        prefix = "/" if path == "/" else path.rstrip("/") + "/"
        result = {}

        for entry in sorted(
            self._entries().values(),
            key=lambda item: item.path,
        ):
            if not entry.path.startswith(prefix):
                continue

            relative = entry.path[len(prefix):]

            if not relative:
                continue

            first_component = relative.split("/", 1)[0]
            is_direct_child = "/" not in relative

            if first_component not in result:
                result[first_component] = {
                    "name": first_component,
                    "is_directory": not is_direct_child
                    or entry.file_type == MachineFile.FileType.DIRECTORY,
                }

            elif is_direct_child:
                result[first_component]["is_directory"] = (
                    entry.file_type == MachineFile.FileType.DIRECTORY
                )

        return sorted(
            result.values(),
            key=lambda item: (
                not item["is_directory"],
                item["name"].casefold(),
            ),
        )

    def parent_path(self, path: str) -> str:
        return str(PurePosixPath(path).parent)