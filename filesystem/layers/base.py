"""Базовый класс слоя (стейта) и описание его аргументов.

Здесь только описание: имя, пояснение и список аргументов. Поведение
слоя (ответы на команды, снятие) добавится отдельными шагами.
"""

from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, ClassVar


@dataclass(frozen=True)
class Param:
    """Аргумент слоя.

    positional=True: главный аргумент, пишется без имени
        (`encrypted hunter2`). Такой может быть только один.
    Остальные пишутся как имя=значение.
    type: str, int, float или bool.
    unlock=True: чтобы снять слой, игрок должен назвать это значение
        (пароль, сдвиг). Слой без таких аргументов снимается просто
        подходящей командой.
    """

    name: str
    type: type = str
    required: bool = False
    default: Any = None
    positional: bool = False
    unlock: bool = False
    help: str = ""


class BaseState:
    name: ClassVar[str] = ""
    summary: ClassVar[str] = ""
    params: ClassVar[tuple[Param, ...]] = ()

    # Свои подстановки слоя в текстах: {attempts_left}. Значения его
    # аргументов доступны и так, по имени аргумента.
    placeholders: ClassVar[tuple[str, ...]] = ()

    # Ответы слоя по умолчанию на информационные команды:
    # {"имя команды": "текст"}. Текст автора слоя (`ftyp: ...` в описании
    # файла) перекрывает их. Словарь не менять, а переопределять целиком.
    answers: ClassVar[Mapping[str, str]] = MappingProxyType({})

    # Что слой делает по умолчанию на события. Пишется тем же языком, что
    # и хуки в описании файла, только блоки `on событие:`. Если автор файла
    # написал свой `on событие:`, он целиком заменяет умолчание этого события.
    #
    #     default_hooks = """
    #     on attempt: say "Осталось попыток: {attempts_left}"
    #     on fail: add damaged
    #     """
    default_hooks: ClassVar[str] = ""

    @classmethod
    def signature(cls) -> str:
        """Как слой пишется в тексте: `encrypted <password> [attempts=3]`."""
        parts = [cls.name]

        for p in cls.params:
            if p.positional:
                parts.append(f"<{p.name}>" if p.required else f"[{p.name}]")
            elif p.required:
                parts.append(f"{p.name}=<значение>")
            else:
                shown = "…" if p.default is None else p.default
                parts.append(f"[{p.name}={shown}]")

        return " ".join(parts)

    @classmethod
    def check_unlock(
        cls, params: Mapping[str, Any], given: Mapping[str, Any]
    ) -> tuple[str, ...]:
        """Подходят ли значения игрока (`given`, уже приведённые к типам)
        к слою. Возвращает имена аргументов, которые не названы или названы
        неверно. Пустой кортеж -- слой можно снимать."""
        return tuple(
            p.name
            for p in cls.params
            if p.unlock and given.get(p.name) != params.get(p.name)
        )

    @classmethod
    def max_attempts(cls, params: Mapping[str, Any]) -> int | None:
        """Сколько неудачных попыток снять слой разрешено. None -- без
        ограничения. Когда попытки кончаются, срабатывает событие fail."""
        return None