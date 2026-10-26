"""Вложения письма: что показать игроку и сохранение файла на машину."""
from django.db import IntegrityError, transaction
from django.urls import get_script_prefix, reverse

from filesystem.models import SessionFile

from .models import Attachment


def _prefix(path):
    return get_script_prefix().rstrip("/") + path


def player_has_file(session, machine_file):
    """Файл уже лежит у игрока в сессии (и не удалён)."""
    if session is None:
        return False
    return SessionFile.objects.filter(session=session, file=machine_file, deleted_at__isnull=True).exists()


def payload(attachment, session=None):
    """Вложение для окна почты: подпись, вид и адреса действий."""
    data = {"id": attachment.pk, "kind": attachment.kind, "label": attachment.label}

    if attachment.kind == Attachment.Kind.ASSET:
        viewer_url = reverse("asset_viewer:viewer", kwargs={"public_id": attachment.asset.public_id})
        content_url = reverse("asset_viewer:content", kwargs={"public_id": attachment.asset.public_id})
        data.update({"open": viewer_url, "download": content_url + "?download=1"})
    elif attachment.kind == Attachment.Kind.FILE:
        data.update({
            "path": attachment.machine_file.path,
            "open": reverse("mail:open", args=[attachment.pk]),
            "save": reverse("mail:save", args=[attachment.pk]),
            "saved": player_has_file(session, attachment.machine_file),
        })
    else:
        data["open"] = _prefix(attachment.path)

    return data


def session_file_of(session, machine_file):
    """Запись игрока о файле (его прогресс и путь) или None, если файл у него не сохранён."""
    if session is None:
        return None
    return SessionFile.objects.filter(session=session, file=machine_file, deleted_at__isnull=True).first()


class SaveError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


@transaction.atomic
def save_to_machine(session, attachment):
    """Положить файл вложения в файловую систему игрока. Возвращает путь файла в сессии."""
    machine_file = attachment.machine_file

    if attachment.kind != Attachment.Kind.FILE or machine_file is None:
        raise SaveError("this attachment cannot be saved to the machine", 400)

    if session.profile.machine_id != machine_file.machine_id:
        raise SaveError("this file belongs to another machine", 409)

    row = SessionFile.objects.filter(session=session, file=machine_file).first()

    if row is None:
        try:
            row = SessionFile.objects.create(session=session, file=machine_file)
        except IntegrityError:
            raise SaveError("the path is already taken on this machine", 409)
    elif row.deleted_at is not None:
        row.deleted_at = None
        row.save(update_fields=["deleted_at"])

    return row.path
