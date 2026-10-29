"""Домашняя папка записи: с неё начинается оболочка и к ней ведёт «~» и «cd» без аргументов.

Это место home машины (machines/world/places.py). Если такой папки в виде машины нет, оболочка начинается с /home, как раньше.
"""
from machines.world import places

LEGACY_HOME = "/home"


def home_of(session):
    from filesystem.machine_view import view_for

    machine = session.profile.machine
    found = places.resolve(machine, "home", session.profile.login)
    if found and view_for(machine, session.user).is_directory(found):
        return found
    return LEGACY_HOME
