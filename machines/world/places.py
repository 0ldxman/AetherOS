"""Именованные места машины: где лежат ключи записи, рабочий стол, корзина, конфиги, логи.

Движок не знает путей, а спрашивает место по имени (``resolve(machine, "secrets", login="ivan")``). Порядок: переопределение на
машине (``Place`` с ``machine``), значение типа системы (``Place`` с ``system_type``), умолчание ниже. Свои имена автор
добавляет в БД: движок их не использует, но на них можно ссылаться из слоёв, хуков и сцен.

В шаблоне: ``{login}`` (логин записи) и ``{home}`` (место ``home``).
"""
import re

from django.db.models import Q

from filesystem.names import normalize_mount
from machines import memo
from machines.models import Place

DEFAULTS = {
    "home": "/home/{login}",
    "secrets": "{home}/.secrets",
    "desktop": "{home}/Desktop",
    "trash": "{home}/.trash",   # своя у каждой записи; общую на машину задаёт место trash машины или типа системы
    "config": "/etc/aether",
    "logs": "/var/log",
    "temp": "/tmp",
}

_VARIABLE = re.compile(r"\{(\w+)\}")
_DEPTH = 5            # вложенность подстановок {home} внутри {home}: защита от циклов


def _templates(machine):
    """Все заданные места машины: тип системы, поверх него переопределения машины (один запрос на запрос игрока)."""
    def load():
        found = {}
        rows = Place.objects.filter(Q(machine=machine) | Q(system_type__code=machine.system)).values_list("machine_id", "name", "path")
        for machine_id, name, path in sorted(rows, key=lambda row: row[0] is not None):               # места машины идут после типа
            found[name] = path
        return found

    return memo.cached(("places", machine.pk, machine.system), load)


def template(machine, name):
    """Шаблон места: машина, тип системы, умолчание. None, если такого места нет нигде."""
    return _templates(machine).get(name, DEFAULTS.get(name))


def resolve(machine, name, login=None, _depth=0):
    """Канонический путь места или None. Без ``login`` место с {login} и {home} (своё у каждой записи) не разрешается."""
    text = template(machine, name)
    if text is None or _depth > _DEPTH:
        return None

    def substitute(match):
        key = match.group(1)
        if key == "login":
            return login or ""
        value = resolve(machine, key, login, _depth + 1) if key != name else None
        return value if value is not None else match.group(0)

    expanded = _VARIABLE.sub(substitute, text)
    if "{" in expanded or (login is None and "{login}" in text):
        return None
    return normalize_mount(expanded)


def per_login(machine, name):
    """Своё ли место у каждой записи (в шаблоне есть {login} или {home})."""
    text = template(machine, name) or ""
    return "{login}" in text or "{home}" in text
