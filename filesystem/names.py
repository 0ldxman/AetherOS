"""Имена и пути внутри тома: проверка и приведение к одному виду.

Путь внутри тома хранится без ведущего слэша и без пустых частей (``etc/aether/access.conf``), корень это пустая строка.
Точка монтирования на машине хранится абсолютной (``/mnt/harbor``); диск Windows-подобной машины хранится как ``/C:``.
"""
import re

from django.core.exceptions import ValidationError

MAX_NAME = 255
DRIVE = re.compile(r"^[A-Za-z]:$")


def validate_name(value):
    """Имя файла или папки: без слэшей, двоеточия (оно разделяет путь в ссылках и обозначает диск), служебных точек."""
    if not value or not value.strip():
        raise ValidationError("Имя не может быть пустым.")
    if value != value.strip():
        raise ValidationError("Имя не должно начинаться и заканчиваться пробелом.")
    if value in (".", ".."):
        raise ValidationError("Имя не может быть «.» или «..».")
    if len(value) > MAX_NAME:
        raise ValidationError(f"Имя длиннее {MAX_NAME} символов.")
    for bad in ("/", "\\", ":", "\x00"):
        if bad in value:
            raise ValidationError(f"В имени запрещён символ {bad!r}.")


def split(path):
    """Части пути без пустых; «.» и «..» запрещены."""
    parts = [part for part in re.split(r"[\\/]+", (path or "").strip()) if part]
    if any(part in (".", "..") for part in parts) or any("\x00" in part for part in parts):
        raise ValidationError("В пути не может быть «.» и «..».")
    return parts


def normalize_inner(path):
    """Путь внутри тома: ``/a//b/`` -> ``a/b``, пусто -> корень."""
    return "/".join(split(path))


def normalize_mount(path):
    """Точка монтирования: ``mnt/harbor`` -> ``/mnt/harbor``, ``C:\\Users`` -> ``/C:/Users``, пусто остаётся пустым (в файловую
    систему том не попадает)."""
    if not (path or "").strip():
        return ""
    parts = split(path)
    for index, part in enumerate(parts):
        if DRIVE.match(part):
            if index:
                raise ValidationError("Диск (C:) может быть только в начале пути.")
            parts[index] = part[0].upper() + ":"
        elif ":" in part:
            raise ValidationError("Двоеточие допустимо только в обозначении диска (C:).")
    return "/" + "/".join(parts)
