"""Файл приложения: объект формата app. Его текст это строки «ключ значение», по одной на параметр:

    label console
    glyph >_
    suffix .sh
    path /apps/terminal/
    order 3

Файл лежит на рабочем столе записи (место desktop), и иконка на столе есть, пока файл виден игроку: условие доступа у файла то же, что у
любого другого (ключи объекта и размещения). Неизвестные строки пропускаются, пустые и начинающиеся с # тоже.
"""
import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError

APP_FORMAT = "app"


VOLUME = re.compile(r"^(?:(?P<host>[^:\s/]+):)?(?P<path>/\S*)(?:\s+as\s+(?P<title>.+?))?(?:\s+user=(?P<user>\S+))?$")


@dataclass(frozen=True)
class VolumeLine:
    """volume archive-srv:/srv/harbor as Harbor user=reader: хост (пусто: эта машина), путь на нём, название раздела, запись хоста."""

    host: str
    path: str
    title: str
    user: str


@dataclass(frozen=True)
class AppSpec:
    label: str
    glyph: str
    suffix: str
    path: str
    order: int = 0
    volumes: tuple = ()          # строки volume файла вики: что вики подключает


def normalize_suffix(value):
    """Расширение приложения всегда с точкой: «db» и «.db» это одно и то же «.db», пустое остаётся пустым."""
    value = (value or "").strip().lstrip(".")
    return f".{value}" if value else ""


def parse(text):
    """AppSpec из текста файла; ValidationError, если чего-то нет или путь не ведёт внутрь проекта."""
    from machines.paths import validate_internal_path

    values, volumes = {}, []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition(" ")
            if key.lower() == "volume":
                found = VOLUME.match(value.strip())
                if found is None:
                    raise ValidationError({"body": f"Строка «{line}»: нужно volume хост:/путь [as Название] [user=запись]."})
                path = found["path"].rstrip("/") or "/"
                volumes.append(VolumeLine(found["host"] or "", path, (found["title"] or "").strip(), found["user"] or ""))
                continue
            values.setdefault(key.lower(), value.strip())

    for key, title in (("label", "название"), ("glyph", "значок"), ("path", "адрес")):
        if not values.get(key):
            raise ValidationError({"body": f"В файле приложения нет строки «{key}» ({title})."})
    if len(values["label"]) > 64 or len(values["glyph"]) > 8:
        raise ValidationError({"body": "Название длиннее 64 знаков или значок длиннее 8."})
    try:
        order = int(values.get("order") or 0)
    except ValueError:
        raise ValidationError({"body": "Порядок «order» это число."})

    try:
        validate_internal_path(values["path"])
    except ValidationError as error:
        raise ValidationError({"body": error.message_dict["path"]})
    return AppSpec(values["label"], values["glyph"], normalize_suffix(values.get("suffix")), values["path"], order, tuple(volumes))


def render(label, glyph, path, suffix="", order=0, volumes=()):
    """Текст файла приложения (volumes: готовые строки после слова volume)."""
    lines = [f"label {label}", f"glyph {glyph}", f"path {path}", *(f"volume {line}" for line in volumes)]
    if suffix:
        lines.append(f"suffix {normalize_suffix(suffix)}")
    if order:
        lines.append(f"order {order}")
    return "\n".join(lines) + "\n"
