"""Реестр слоёв: имя в тексте -> класс слоя.

    @register
    class Encrypted(BaseState):
        name = "encrypted"
        ...
"""

import re

from filesystem.states.base import BaseState

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_TYPES = (str, int, float, bool)


class StateRegistry:
    def __init__(self):
        self._states: dict[str, type[BaseState]] = {}

    def register(self, cls: type[BaseState]) -> type[BaseState]:
        """Декоратор для класса слоя. Ошибки в описании слоя (это работа
        программиста, не админа) падают сразу при импорте."""
        if not _NAME.match(cls.name or ""):
            raise ValueError(
                f"{cls.__name__}: имя слоя должно быть вида 'encrypted' "
                f"(строчные латинские буквы, цифры, _), а не {cls.name!r}"
            )

        if cls.name in self._states:
            raise ValueError(f"слой {cls.name!r} уже зарегистрирован")

        names = [p.name for p in cls.params]

        if len(names) != len(set(names)):
            raise ValueError(f"{cls.name}: повторяющиеся имена аргументов")

        if sum(p.positional for p in cls.params) > 1:
            raise ValueError(
                f"{cls.name}: главный (positional) аргумент может быть только один"
            )

        for p in cls.params:
            if not _NAME.match(p.name):
                raise ValueError(f"{cls.name}: плохое имя аргумента {p.name!r}")

            if p.type not in _TYPES:
                raise ValueError(
                    f"{cls.name}.{p.name}: тип должен быть str, int, float или bool"
                )

        self._states[cls.name] = cls
        return cls

    def get(self, name: str) -> type[BaseState] | None:
        return self._states.get(name)

    def names(self) -> list[str]:
        return sorted(self._states)

    def describe(self) -> str:
        """Справка по слоям для админки, строится из самих классов."""
        blocks = []

        for name in self.names():
            cls = self._states[name]
            lines = [cls.signature()]

            if cls.summary:
                lines.append(f"    {cls.summary}")

            for p in cls.params:
                if p.help:
                    lines.append(f"    {p.name}: {p.help}")

            if cls.default_hooks.strip():
                lines.append("    по умолчанию:")

                for row in cls.default_hooks.strip().splitlines():
                    if row.strip():
                        lines.append(f"        {row.strip()}")

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)


registry = StateRegistry()
register = registry.register