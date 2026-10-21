from pathlib import PurePosixPath

from filesystem.models import MachineFile


class VirtualFilesystem:
    def __init__(self, context):
        self.context = context

    def _query(self):
        return MachineFile.objects.filter(
            machine=self.context.machine,
        )

    def get_file(self, path: str) -> MachineFile | None:
        return self._query().filter(path=path).first()

    def exists(self, path: str) -> bool:
        if path == "/":
            return True

        if self.get_file(path) is not None:
            return True

        prefix = path.rstrip("/") + "/"

        return self._query().filter(
            path__startswith=prefix,
        ).exists()

    def is_directory(self, path: str) -> bool:
        if path == "/":
            return True

        file = self.get_file(path)

        if file is not None:
            return file.file_type == MachineFile.FileType.DIRECTORY

        prefix = path.rstrip("/") + "/"

        return self._query().filter(
            path__startswith=prefix,
        ).exists()

    def list_directory(self, path: str) -> list[dict]:
        if not self.is_directory(path):
            raise NotADirectoryError(path)

        prefix = "/" if path == "/" else path.rstrip("/") + "/"
        result = {}

        for file in self._query().filter(
            path__startswith=prefix,
        ).order_by("path"):
            relative = file.path[len(prefix):]

            if not relative:
                continue

            first_component = relative.split("/", 1)[0]
            is_direct_child = "/" not in relative

            if first_component not in result:
                result[first_component] = {
                    "name": first_component,
                    "is_directory": not is_direct_child
                    or file.file_type == MachineFile.FileType.DIRECTORY,
                }

            elif is_direct_child:
                result[first_component]["is_directory"] = (
                    file.file_type == MachineFile.FileType.DIRECTORY
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