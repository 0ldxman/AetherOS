"""Общий кэш ответов карты: цвета провинций, подписи стран и засечки таймлайна одинаковы для всех игроков
и меняются только когда правят владения, провинции или страны. Любая такая правка поднимает версию
(сигналы ниже), ещё у записи есть срок жизни на случай массовых импортов, которые сигналов не шлют."""
from django.core.cache import cache
from django.http import JsonResponse

VERSION_KEY = "map:version"
TTL = 600


def bump_version():
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 1, None)


def shared_json(name, variant, compute):
    key = f"map:{name}:{cache.get(VERSION_KEY, 0)}:{variant}"
    data = cache.get(key)
    if data is None:
        data = compute()
        cache.set(key, data, TTL)
    response = JsonResponse(data, safe=False)
    # браузеру и прокси тоже можно подержать: правки на карте не срочные
    response["Cache-Control"] = "public, max-age=60"
    return response
