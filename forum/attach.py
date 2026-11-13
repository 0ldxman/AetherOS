"""Вложения форума: снимок файла игрока при отправке и сохранение вложения на диск читателя (как вложение письма, но для всех читателей)."""
import posixpath

from forum.logic import ForumError
from forum.models import Attachment
from secure.access import satisfied

MAX_PER_POST = 2
MAX_TEXT = 64_000
MAX_DATA = 256_000


def snapshot(entry, keys):
    """Что кладётся во вложение: {"name", "item", "content", "data", "size"}. Ключи, папки и закрытое отсюда не уходят."""
    from filesystem.models import KEY_FORMAT

    if entry is None or entry.is_dir:
        raise ForumError("нет такого файла")
    if not all(satisfied(condition, keys) for condition in entry.conditions):
        raise ForumError(f"{entry.name}: файл закрыт")
    item = entry.item
    if item is not None and (item.format == KEY_FORMAT or item.keys.exists()):
        raise ForumError(f"{entry.name}: ключи прикладывать нельзя")
    if item is not None:
        content = entry.text_override
        size = len(content if content is not None else item.body or "")
        data = None
    elif entry.own_data is not None:
        content, data = None, entry.own_data
        size = len(data)
    else:
        content, data = entry.own_text or "", None
        size = len(content)
    if size > (MAX_DATA if data is not None else MAX_TEXT):
        raise ForumError(f"{entry.name}: слишком большой файл")
    return {"name": entry.name[:128], "item": item, "content": content, "data": data, "size": size}


def attach(post, snapshots):
    if len(snapshots) > MAX_PER_POST:
        raise ForumError(f"не больше {MAX_PER_POST} файлов")
    return [Attachment.objects.create(post=post, **found) for found in snapshots]


def save_to_disk(box, attachment):
    """Положить копию вложения в домашнюю папку игрока (рядом с таким же именем добавляется -2, -3). Возвращает путь."""
    from machines.world import places

    if box.user is None:
        raise ForumError("сохранять файлы могут только игроки")
    home = places.resolve(box.machine, "home", box.login) or "/"
    stem, dot, extension = attachment.name.rpartition(".")
    if not dot:
        stem, extension = attachment.name, ""
    path, number = posixpath.join(home, attachment.name), 1
    while box.view.get(path) is not None:
        number += 1
        path = posixpath.join(home, f"{stem}-{number}{dot}{extension}")
    rights = {"owner": box.login, "group": "", "mode": "644"}
    if attachment.item_id is not None:
        box.view.put_item(path, attachment.item, "", attachment.content, rights)
    elif attachment.data is not None:
        box.view.put_data(path, bytes(attachment.data), "", rights)
    else:
        box.view.put_text(path, attachment.content or "", "", rights)
    return path
