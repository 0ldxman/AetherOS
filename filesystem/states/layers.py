"""Встроенные слои (шаг 4): только описание и аргументы.

Поведения здесь пока нет: ни ответов на команды, ни снятия. Слой
регистрируется в общем реестре, после чего его можно писать в тексте
стека и проверять через compile_text.
"""

from filesystem.states.base import BaseState, Param
from filesystem.states.compiler import validate_defaults
from filesystem.states.registry import register


@register
class Corrupted(BaseState):
    name = "corrupted"
    summary = "Файл повреждён."


@register
class Damaged(BaseState):
    name = "damaged"
    summary = (
        "Файл повреждён по ошибке игрока (или после восстановления с диска). "
        "Обычно добавляется хуком: add damaged."
    )


@register
class Encrypted(BaseState):
    name = "encrypted"
    summary = "Файл зашифрован паролем."
    placeholders = ("attempts_left",)
    params = (
        Param(
            "password",
            str,
            required=True,
            positional=True,
            unlock=True,
            help="пароль, который нужно ввести",
        ),
        Param(
            "attempts",
            int,
            default=3,
            help="сколько неверных попыток разрешено",
        ),
    )

    @classmethod
    def max_attempts(cls, params):
        return params["attempts"]


@register
class Base64(BaseState):
    name = "base64"
    summary = "Содержимое закодировано в base64."


@register
class Shifted(BaseState):
    name = "shifted"
    summary = "Данные сдвинуты: нужно знать, с какого места и сколько читать."
    params = (
        Param("skip", int, required=True, unlock=True, help="сколько блоков пропустить"),
        Param("count", int, required=True, unlock=True, help="сколько блоков взять"),
    )


# Ошибка в default_hooks любого слоя должна падать сразу при запуске.
validate_defaults()