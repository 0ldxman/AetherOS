"""Авторы и роли: что делает суперадмин на экране «Команда». Проверка, что делает это суперадмин, в API (team.rights)."""
from django.contrib.auth import get_user_model
from django.db import transaction

from team import rights
from team.models import Role


class TeamError(Exception):
    pass


def authors():
    return get_user_model().objects.filter(is_staff=True).select_related("role").order_by("-is_superuser", "username")


def find_users(text, limit=20):
    """Пользователи не из команды по части имени: кого можно сделать автором."""
    found = get_user_model().objects.filter(is_staff=False, is_active=True)
    if text:
        found = found.filter(username__icontains=text)
    return list(found.order_by("username")[:limit])


def save_role(role, name, note, sections, actions):
    role.name = name.strip()
    role.note = note
    role.rights = {section: level for section, level in sections.items() if level != rights.NONE}
    role.actions = sorted(set(actions))
    role.full_clean()
    role.save()
    return role


def delete_role(role):
    """Удалить роль. Её авторы остаются без роли, то есть только смотрят."""
    role.delete()


@transaction.atomic
def set_author(actor, user, role):
    """Сделать пользователя автором с ролью (или сменить роль автора)."""
    if user.is_superuser:
        raise TeamError("Роль суперадмина не меняется: у него все права.")
    user.is_staff = True
    user.role = role
    user.save(update_fields=["is_staff", "role"])
    return user


def remove_author(actor, user):
    """Убрать из команды: пользователь остаётся игроком."""
    if user.is_superuser or user.pk == actor.pk:
        raise TeamError("Суперадмина и себя убрать из команды нельзя.")
    user.is_staff = False
    user.role = None
    user.save(update_fields=["is_staff", "role"])
