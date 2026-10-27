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
    summary = "Файл зашифрован: снимается паролем (ward файл пароль) или ключом (ward -k ключ файл)."
    placeholders = ("attempts_left",)
    params = (
        Param(
            "password",
            str,
            positional=True,
            unlock=True,
            help="пароль, который нужно ввести (можно не задавать, если файл открывается ключом)",
        ),
        Param(
            "key",
            str,
            unlock=True,
            help="slug ключа, которым файл расшифровывается (ключ игрок достаёт командой kex: ward -k)",
        ),
        Param(
            "attempts",
            int,
            default=3,
            help="сколько неверных попыток разрешено",
        ),
    )

    @classmethod
    def check_unlock(cls, params, given):
        """Подходит пароль или ключ: названный ключ сравнивается с ключом слоя, иначе пароль с паролем слоя."""
        if given.get("key"):
            wanted = str(params.get("key") or "").strip().lower()
            return () if wanted and str(given["key"]).strip().lower() == wanted else ("key",)
        wanted = params.get("password")
        return () if wanted not in (None, "") and given.get("password") == wanted else ("password",)

    @classmethod
    def max_attempts(cls, params):
        return params["attempts"]


@register
class Shifted(BaseState):
    name = "shifted"
    summary = "Настоящие данные лежат со сдвигом, перед ними шум: нужно найти, где они начинаются, и вырезать их командой blk."
    params = (
        Param("skip", int, required=True, unlock=True, help="сколько блоков (по 512 байт) шума перед данными"),
        Param("count", int, help="сколько блоков занимают данные (справка автору: снимает слой начало окна, а не его длина)"),
        Param("out", str, help="имя файла, который получится при верной вырезке (blk): путь рядом с исходником или абсолютный"),
    )


@register
class Binary(BaseState):
    name = "binary"
    summary = (
        "Внутри настоящий текст, но в необычной кодировке (utf16, hex, rot13, gzip, morse): нужно опознать её и "
        "раскодировать командой cvt enc <кодировка> <файл>."
    )
    params = (
        Param(
            "encoding",
            str,
            required=True,
            positional=True,
            unlock=True,
            help="кодировка, в которую завёрнут текст (регистр не важен)",
        ),
    )

    @classmethod
    def check_unlock(cls, params, given):
        wanted = str(params.get("encoding", "")).strip().lower()
        named = str(given.get("encoding", "")).strip().lower()
        return () if wanted and wanted == named else ("encoding",)


@register
class Disguised(BaseState):
    name = "disguised"
    summary = "Файл выдаёт себя за один формат, а на деле другого: его нужно прочитать как настоящий (cvt ext <файл> <файл.формат>)."
    params = (
        Param(
            "format",
            str,
            required=True,
            positional=True,
            unlock=True,
            help="настоящий формат, в который нужно преобразовать файл (регистр не важен)",
        ),
    )

    @classmethod
    def check_unlock(cls, params, given):
        from filesystem.rawview.registry import format_named

        def canonical(text):
            text = str(text).strip().lower().lstrip(".")
            found = format_named(text)
            return found.name if found else text          # jpeg и jpg это один формат

        wanted, named = canonical(params.get("format", "")), canonical(given.get("format", ""))
        return () if wanted and wanted == named else ("format",)


# Ошибка в default_hooks любого слоя должна падать сразу при запуске.
validate_defaults()