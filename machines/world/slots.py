"""Слоты сцен: события, на которых ОС может играть свою сцену (SystemScene) вместо встроенной.

У каждого слота свои подстановки: сцену собирает сервер уже после решения, в неё попадает только то, что игрок и так узнал бы.
Если у ОС нет привязки или сцена не собралась (ошибка в тексте), играет встроенная."""
from dataclasses import dataclass

from machines import memo


@dataclass(frozen=True)
class Slot:
    label: str
    params: dict          # имя подстановки -> подпись для студии


# что можно подставить в приветствие оболочки ОС и в сцену после входа под учётку: имя -> подпись для студии
GREETING_PARAMS = {
    "host": "имя машины", "login": "логин учётки", "os": "код ОС", "os_name": "название ОС", "address": "адрес узла (частота или сетевой)", "serial": "серийный номер",
    "hid": "hid машины", "host_key": "отпечаток ключа узла", "time": "время в мире (UTC)", "freq": "частота учётки, под которой вошли", "date": "дата в мире", "last_login": "прошлый вход этой учётки",
    "uptime": "сколько работает машина", "accounts": "число учёток машины", "sessions": "сколько игроков на машине сейчас",
    "disk_total": "условная ёмкость дисков", "disk_used": "занято на дисках", "disk_percent": "занято, %",
    "unread": "число непрочитанных писем", "mail": "строка про непрочитанную почту", "volumes": "тома машины", "note": "заметка машины",
}


_CONNECT = {"host": "хост, на который входят", "login": "логин учётки", "endpoint": "частота (радио) или порт", "freq": "частота учётки", "os": "код ОС хоста"}

_BOOT = {
    "host": "имя машины", "hid": "hid", "serial": "серийный номер", "address": "адрес узла", "host_key": "отпечаток ключа узла",
    "os": "код ОС", "os_name": "название ОС", "date": "дата в мире", "time": "время в мире (UTC)", "pcr": "хэш измерений загрузки",
}

SLOTS = {
    "bridge.connect": Slot("Подключение: мост, оболочка, перенос", _CONNECT),
    "bridge.denied": Slot("Подключение отклонено", {**_CONNECT, "endpoint": "частота или порт (пусто при поиске)"}),
    "bridge.locked": Slot("Учётка заблокирована", {"host": "хост", "login": "логин учётки", "os": "код ОС хоста"}),
    "bridge.unreachable": Slot("Хост не найден", {"host": "хост", "os": "код ОС"}),
    "bridge.disconnect": Slot("Закрытие подключения", {"host": "хост, с которого уходят", "os": "код ОС хоста"}),
    "bridge.kick": Slot("Обрыв с той стороны", {"host": "хост", "os": "код ОС хоста"}),
    "machine.boot": Slot("Загрузка машины: полная (первый заход)", _BOOT),
    "machine.boot_short": Slot("Загрузка машины: короткая (повторный заход; нет: играет полная)", _BOOT),
    "login.account": Slot("После входа под учётку (идёт за приветствием)", GREETING_PARAMS),
}


def all_params():
    """Все подстановки всех слотов: текст сцены в библиотеке проверяется по ним, а событию подходит только его набор."""
    return {name for slot in SLOTS.values() for name in slot.params}


def _binding(system, slot):
    from machines.models import SystemScene

    return memo.cached(
        ("scene", system, slot),
        lambda: SystemScene.objects.filter(system_type__code=system, slot=slot).select_related("script").first(),
    )


def _play(script, slot, values):
    from machines.models.scenes import resolve_script
    from machines.world.dates import world
    from scenes.script import compile_script

    params = {name: values.get(name, "") for name in SLOTS[slot].params}
    scene, errors = compile_script(script.body, params, world().game_now, resolve_script)
    return None if errors else scene.to_dict()


def custom(slot, system, **values):
    """Сцена ОС для события (список шагов) или None, если у ОС своей нет и играет встроенная."""
    found = _binding(system, slot)
    return None if found is None else _play(found.script, slot, values)


def account_scene(profile, values):
    """Сцена после входа под учётку: своя у учётки, иначе общая у ОС; None, если ни той ни другой."""
    if profile is not None and profile.login_scene_id:
        return _play(profile.login_scene, "login.account", values)
    return custom("login.account", profile.machine.system, **values) if profile is not None else None
