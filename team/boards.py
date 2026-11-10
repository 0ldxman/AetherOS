"""Доски команды и поиск сущностей мира для карточек на доске."""
from django.db.models import Q

from team.models import Board, Draft

ENTITY_LIMIT = 8


class BoardError(Exception):
    pass


def boards():
    return list(Board.objects.select_related("created_by"))


def create(user, title):
    title = (title or "").strip()
    if not title:
        raise BoardError("Назовите доску.")
    return Board.objects.create(title=title[:120], created_by=user)


def rename(board, title):
    title = (title or "").strip()
    if not title:
        raise BoardError("Назовите доску.")
    board.title = title[:120]
    board.save(update_fields=["title", "updated_at"])
    return board


def delete(user, board):
    if board.main:
        raise BoardError("Основную доску не удалить.")
    if not user.is_superuser and board.created_by_id != user.pk:
        raise BoardError("Доску удаляет тот, кто её завёл, или суперадмин.")
    Draft.objects.filter(room=board.room).delete()
    board.delete()


def entities(text):
    """Сущности мира по части названия: [{kind, label, link}] для карточек на доске."""
    from django.contrib.auth import get_user_model

    from filesystem.models import Item, Volume
    from machines.models import Machine, MachineProfile, SceneScript, SystemType

    text = (text or "").strip()
    if not text:
        return []
    found = []
    for machine in Machine.objects.filter(Q(hostname__icontains=text) | Q(name__icontains=text))[:ENTITY_LIMIT]:
        found.append({"kind": "Машина", "label": machine.hostname or machine.name, "link": f"#/machines/{machine.pk}"})
    for profile in MachineProfile.objects.filter(login__icontains=text).select_related("machine")[:ENTITY_LIMIT]:
        found.append({"kind": "Учётка", "label": f"{profile.login}@{profile.machine.hostname}",
                      "link": f"#/machines/{profile.machine_id}/accounts/{profile.pk}"})
    for item in Item.objects.filter(Q(name__icontains=text) | Q(slug__icontains=text))[:ENTITY_LIMIT]:
        found.append({"kind": "Объект", "label": item.name, "link": f"#/items/{item.pk}"})
    for volume in Volume.objects.filter(Q(slug__icontains=text) | Q(label__icontains=text))[:ENTITY_LIMIT]:
        found.append({"kind": "Диск", "label": volume.label or volume.slug, "link": f"#/volumes/{volume.pk}"})
    for system in SystemType.objects.filter(Q(code__icontains=text) | Q(name__icontains=text))[:ENTITY_LIMIT]:
        found.append({"kind": "ОС", "label": system.code, "link": f"#/systems/{system.code}"})
    for scene in SceneScript.objects.filter(Q(slug__icontains=text) | Q(title__icontains=text))[:ENTITY_LIMIT]:
        found.append({"kind": "Сцена", "label": scene.title or scene.slug, "link": f"#/scenes/{scene.slug}"})
    from team.models import Task

    for task in Task.objects.filter(title__icontains=text)[:ENTITY_LIMIT]:
        found.append({"kind": "Задача", "label": task.title, "link": f"#/tasks/{task.pk}"})
    for user in get_user_model().objects.filter(username__icontains=text, is_superuser=False)[:ENTITY_LIMIT]:
        found.append({"kind": "Игрок", "label": user.get_username(), "link": f"#/players/{user.pk}"})
    for row in found:
        row["target"] = row["link"].removeprefix("#/")             # путь API сущности: им задача ссылается на неё
    return found
