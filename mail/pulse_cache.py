"""Кэш ответов почты по читателю: pulse рабочий стол опрашивает каждые несколько секунд, список писем открывается с окном.

Ответ зависит от читателя и от писем. Любое изменение писем, доставок, корзины или отметок
о прочтении поднимает общую версию, и кэши всех читателей устаревают сразу. Время доставки
(available_at) наступает само, без записи в базу, поэтому у записи есть и короткий срок жизни.
Без общего кэша (Redis) версия поднимается только в своём процессе, и срок жизни ограничивает
задержку у остальных.
"""
import hashlib

from django.core.cache import cache

VERSION_KEY = "mail:version"
TTL = 15


def bump_version():
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 1, None)


def _who(viewer):
    owner = f"u{viewer.user.pk}" if viewer.user is not None else f"s{viewer.session_key}"
    keys = ",".join(sorted(viewer.keys))
    return hashlib.md5(f"{owner}|{viewer.address}|{keys}".encode()).hexdigest()


def cached_for_viewer(name, viewer, compute):
    key = f"mail:{name}:{cache.get(VERSION_KEY, 0)}:{_who(viewer)}"
    data = cache.get(key)
    if data is None:
        data = compute()
        cache.set(key, data, TTL)
    return data


def cached_pulse(viewer, compute):
    return cached_for_viewer("pulse", viewer, compute)
