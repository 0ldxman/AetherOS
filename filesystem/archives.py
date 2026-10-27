"""Архивы файловой системы: файл с расширением, под путём которого лежат другие файлы машины.

    /home/archive.pak                    запись архива (нужна, если на нём есть слои; без слоёв её создаёт сама система)
    /home/archive.pak/README.txt         члены архива: обычные файлы машины
    /home/archive.pak/secret.7z          вложенный архив
    /home/archive.pak/secret.7z/key.key  его член

Игрок видит архив одним файлом: войти в него нельзя, а члены по их путям ему недоступны, пока он не распакует архив (pak).
Запись типа «папка» (DIRECTORY) архивом не считается: так автор может сделать обычную папку с точкой в имени.
"""
import posixpath

from django.db.models import Count, Max

from filesystem.models import MachineFile


def has_extension(path):
    """Есть ли у имени расширение (.secrets это скрытая папка, а не расширение)."""
    return bool(posixpath.splitext(posixpath.basename(path.rstrip("/")))[1])


def ancestors(path):
    """Пути выше path, кроме корня: /a/b/c -> /a/b, /a."""
    found, current = [], posixpath.dirname(path)
    while current and current != "/":
        found.append(current)
        current = posixpath.dirname(current)
    return found


def find(records):
    """Пути-архивы среди записей машины. records: {путь: тип файла}.

    Архив это путь, под которым что-то лежит, и это либо запись-файл, либо путь без записи, но с расширением."""
    below = {up for path in records for up in ancestors(path)}
    return {
        path for path in below
        if records.get(path) == MachineFile.FileType.FILE or (path not in records and has_extension(path))
    }


def hidden(path, archives):
    """Лежит ли path внутри какого-нибудь архива (сам архив не считается)."""
    return any(path.startswith(archive + "/") for archive in archives)


def ensure_records(machine, records):
    """Записи для архивов без записи (файл без слоёв): создаются при первом обращении. Возвращает созданные MachineFile."""
    created = []
    for path in sorted(find(records) - set(records)):
        item, _ = MachineFile.objects.get_or_create(
            machine=machine, path=path, defaults={"file_type": MachineFile.FileType.FILE}
        )
        created.append(item)
    return created


def below(machine_file):
    """Все файлы машины под путём этой записи."""
    return MachineFile.objects.filter(machine_id=machine_file.machine_id, path__startswith=machine_file.path.rstrip("/") + "/")


def is_archive(machine_file):
    """Файл (запись-файл) с расширением, под которым что-то лежит."""
    return (
        machine_file.file_type == MachineFile.FileType.FILE
        and has_extension(machine_file.path)
        and below(machine_file).exists()
    )


def stamp(machine_file):
    """Что меняется вместе с содержимым архива: число файлов под ним и время последней правки."""
    data = below(machine_file).aggregate(n=Count("id"), last=Max("updated_at"))
    return f"{data['n']}:{data['last'].timestamp() if data['last'] else 0}"


def members(machine_file):
    """Члены архива: [(путь внутри архива, MachineFile)] только файлы, без содержимого вложенных архивов."""
    prefix = machine_file.path.rstrip("/") + "/"
    items = list(below(machine_file).order_by("path"))
    nested = {path for path in find({item.path: item.file_type for item in items}) if path.startswith(prefix)}
    return [
        (item.path[len(prefix):], item)
        for item in items
        if item.file_type == MachineFile.FileType.FILE and not hidden(item.path, nested)
    ]
