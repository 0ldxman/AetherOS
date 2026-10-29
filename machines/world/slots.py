"""Слоты сцен: события, на которых ОС может играть свою сцену (SystemScene) вместо встроенной.

У каждого слота свои подстановки: сцену собирает сервер уже после решения, в неё попадает только то, что игрок и так узнал бы.
Если у ОС нет привязки или сцена не собралась (ошибка в тексте), играет встроенная."""
from dataclasses import dataclass

from machines import memo


@dataclass(frozen=True)
class Slot:
    label: str
    params: dict          # имя подстановки -> подпись для студии


_CONNECT = {"host": "хост, на который входят", "login": "логин учётки", "endpoint": "частота (радио) или порт", "freq": "частота учётки", "os": "код ОС хоста"}

SLOTS = {
    "bridge.connect": Slot("Подключение: мост, оболочка, перенос", _CONNECT),
    "bridge.denied": Slot("Подключение отклонено", {**_CONNECT, "endpoint": "частота или порт (пусто при поиске)"}),
    "bridge.locked": Slot("Учётка заблокирована", {"host": "хост", "login": "логин учётки", "os": "код ОС хоста"}),
    "bridge.unreachable": Slot("Хост не найден", {"host": "хост", "os": "код ОС"}),
    "bridge.disconnect": Slot("Закрытие подключения", {"host": "хост, с которого уходят", "os": "код ОС хоста"}),
    "bridge.kick": Slot("Обрыв с той стороны", {"host": "хост", "os": "код ОС хоста"}),
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


def custom(slot, system, **values):
    """Сцена ОС для события (список шагов) или None, если у ОС своей нет и играет встроенная."""
    from machines.models.scenes import resolve_script
    from machines.world.dates import world
    from scenes.script import compile_script

    found = _binding(system, slot)
    if found is None:
        return None
    params = {name: values.get(name, "") for name in SLOTS[slot].params}
    scene, errors = compile_script(found.script.body, params, world().game_now, resolve_script)
    return None if errors else scene.to_dict()
