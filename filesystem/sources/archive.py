"""Архив: файл, под путём которого лежат другие файлы машины. Адреса у него нет."""
from filesystem.sources.base import Payload


def claims(machine_file):
    from filesystem import archives

    return archives.is_archive(machine_file)


def payload(machine_file, keys, reader, viewer):
    """Архив: заголовок pak, таблица (имя, размер, смещение) и данные членов. Данные члена это его собственные байты с его
    слоями, у вложенного архива это его архив целиком. Тело строится лениво: для размера и кэша хватает отпечатка."""
    from filesystem import archives
    from filesystem.rawview import formats
    from filesystem.rawview.generate import build_raw

    def build():
        found = [(name, build_raw(item, "", keys, reader, viewer).data) for name, item in archives.members(machine_file)]
        table, offset = b"", 0
        header = len(formats.magic("pak")) + 2 + sum(2 + len(name.encode()) + 8 for name, _ in found)
        for name, data in found:
            table += len(name.encode()).to_bytes(2, "big") + name.encode() + len(data).to_bytes(4, "big") + (header + offset).to_bytes(4, "big")
            offset += len(data)
        return formats.magic("pak") + len(found).to_bytes(2, "big") + table + b"".join(data for _, data in found)

    return Payload(kind="archive", layout="archive", real=True, build=build, stamp=f"archive:{machine_file.pk}:{archives.stamp(machine_file)}")
