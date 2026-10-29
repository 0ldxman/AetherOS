"""Вложения письма: что показать игроку и сохранение файла на машину."""
import posixpath

from django.urls import get_script_prefix, reverse

from filesystem.machine_view import FILE, Entry, MachineView, view_for
from machines.world import places

from mail.models import Attachment


def _prefix(path):
    return get_script_prefix().rstrip("/") + path


def target_path(session, attachment):
    """Куда вложение ложится у игрока: названный автором путь, а без него домашняя папка под именем объекта."""
    item = attachment.item
    login = session.profile.login if session is not None else ""
    home = (places.resolve(session.profile.machine, "home", login) if session is not None else None) or "/home"
    path = (attachment.save_path or "").strip()
    if not path:
        return posixpath.join(home, item.default_filename)
    return path if path.startswith("/") else posixpath.join(home, path)


def saved_entry(session, attachment):
    """Файл вложения в виде машины игрока, если он уже сохранён (по назначенному пути лежит этот объект), иначе None."""
    if session is None:
        return None
    found = view_for(session.profile.machine, session.user).get(target_path(session, attachment))
    return found if found is not None and found.item is not None and found.item.pk == attachment.item_id else None


def virtual_entry(session, attachment):
    """Файл вложения так, как он выглядел бы у игрока, но без сохранения: для окна просмотра."""
    return Entry(path=target_path(session, attachment), kind=FILE, item=attachment.item)


def player_has_file(session, attachment):
    """Файл уже лежит у игрока."""
    return saved_entry(session, attachment) is not None


def payload(attachment, session=None):
    """Вложение для окна почты: подпись, вид и адреса действий."""
    data = {"id": attachment.pk, "kind": attachment.kind, "label": attachment.label}

    if attachment.kind == Attachment.Kind.ASSET:
        viewer_url = reverse("asset_viewer:viewer", kwargs={"public_id": attachment.asset.public_id})
        content_url = reverse("asset_viewer:content", kwargs={"public_id": attachment.asset.public_id})
        data.update({"open": viewer_url, "download": content_url + "?download=1"})
    elif attachment.kind == Attachment.Kind.FILE:
        data.update({
            "path": target_path(session, attachment),
            "open": reverse("mail:open", args=[attachment.pk]),
            "save": reverse("mail:save", args=[attachment.pk]),
            "saved": player_has_file(session, attachment),
        })
    else:
        data["open"] = _prefix(attachment.path)

    return data


class SaveError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def save_to_machine(session, attachment):
    """Положить файл вложения в файловую систему игрока. Возвращает путь файла у игрока."""
    if attachment.kind != Attachment.Kind.FILE or attachment.item is None:
        raise SaveError("this attachment cannot be saved to the machine", 400)

    view = view_for(session.profile.machine, session.user)
    path = target_path(session, attachment)
    found = view.get(path)
    if found is not None:
        if found.item is not None and found.item.pk == attachment.item_id and not found.is_dir:
            return path
        raise SaveError("the path is already taken on this machine", 409)

    view.put_item(path, attachment.item)
    return path
