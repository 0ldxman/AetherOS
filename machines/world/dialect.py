"""Диалект путей: как машина показывает и принимает пути. Внутри пути канонические (``/home/ivan``, ``/C:/Users/ivan``).

Шаблоны мест (``{home}/.secrets``) тоже приводятся к каноническому виду, но подстановки остаются как есть: путь из них
собирается и проверяется уже после подстановки (machines.world.places).
"""
import re

UNIX = "unix"
WINDOWS = "windows"

_DRIVE_START = re.compile(r"^[A-Za-z]:(?=[\\/]|$)")


def to_canonical(path):
    """Путь или шаблон, как его ввели (``C:\\Users\\{login}`` или ``/home/{login}``), -> канонический (``/C:/Users/{login}``)."""
    text = (path or "").strip().replace("\\", "/")
    if not text:
        return ""
    if _DRIVE_START.match(text):
        text = "/" + text[0].upper() + text[1:]
    parts = [part for part in text.split("/") if part]
    prefix = "/" if text.startswith("/") else ""
    return prefix + "/".join(parts)


def to_display(path, style):
    """Канонический путь -> вид в диалекте системы: ``/C:/Users/ivan`` -> ``C:\\Users\\ivan``."""
    if style != WINDOWS or not path:
        return path
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "\\"
    if len(parts[0]) == 2 and parts[0][1] == ":":
        return parts[0] + "\\" + "\\".join(parts[1:])
    return "\\" + "\\".join(parts)
