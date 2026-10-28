"""Архивы: объект, у которого есть члены (ItemMember), то есть другие объекты под путями внутри архива.

Игрок видит архив одним файлом; его члены недоступны, пока он не распакует архив (pak). Архив это обычный файл: его копируют,
переносят и защищают слоями (пароль, повреждение) как любой другой, а члены лежат у объекта и едут вместе с ним.
"""
import hashlib
import posixpath
from dataclasses import replace

from filesystem.machine_view import FILE, Entry


def has_extension(path):
    """Есть ли у имени расширение (.secrets это скрытая папка, а не расширение)."""
    return bool(posixpath.splitext(posixpath.basename(path.rstrip("/")))[1])


def members(view, archive):
    """Члены архива: [(путь внутри архива, запись)]; вложенный архив это один член, без его содержимого."""
    found = []
    for row in archive.item.members.select_related("item").order_by("path"):
        found.append((row.path, Entry(
            path=f"{archive.path.rstrip('/')}/{row.path}", kind=FILE, layer=archive.layer, inner="", placement=None, item=row.item,
        )))
    return found


def stamp(found):
    """Что меняется вместе с содержимым архива: члены и время правки их объектов."""
    parts = [f"{name}:{entry.item.pk}:{entry.item.updated_at.timestamp()}:{len(entry.item.members.all())}" for name, entry in found]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
