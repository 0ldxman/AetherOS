"""Файл приложения: объект формата app. Его текст это строки «ключ значение», по одной на параметр:

    label console
    icon terminal
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


VOLUME = re.compile(r"^(?:(?P<host>[^:\s/]+):)?(?P<path>/\S*|[\w.-]+)(?P<rest>.*)$")      # путь или имя раздачи (хост:имя)
OPTION = re.compile(r"\s+(user|pass|token|key)=(\S+)\s*$")


@dataclass(frozen=True)
class VolumeLine:
    """volume archive-srv:/srv/harbor as Harbor user=reader pass=… token=… key=…: хост (пусто: эта машина), путь на нём, название
    раздела, запись хоста и чем на неё войти — пароль, токен или ключ из папки секретов игрока (по правилам учётки, как rshell)."""

    host: str
    path: str
    title: str
    user: str
    password: str = ""
    token: str = ""
    key: str = ""


def parse_volume(text):
    """VolumeLine из «хост:/путь [as Название] [user=…] [pass=…] [token=…] [key=…]» или None."""
    found = VOLUME.match((text or "").strip())
    if found is None:
        return None
    rest, options = found["rest"], {}
    while (option := OPTION.search(rest)) is not None:
        options.setdefault(option[1], option[2])
        rest = rest[:option.start()]
    rest = rest.strip()
    if rest and not rest.startswith("as "):
        return None
    if not found["path"].startswith("/") and not found["host"]:
        return None                                              # раздача — только с хостом
    path = found["path"].rstrip("/") or "/"
    return VolumeLine(found["host"] or "", path, rest[3:].strip(), options.get("user", ""), options.get("pass", ""),
                      options.get("token", ""), options.get("key", ""))


@dataclass(frozen=True)
class AppSpec:
    label: str
    icon: str
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
    from machines.world.paths import validate_internal_path

    values, volumes = {}, []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition(" ")
            if key.lower() == "volume":
                spec = parse_volume(value)
                if spec is None:
                    raise ValidationError({"body": f"Строка «{line}»: нужно volume хост:/путь [as Название] [user=запись] "
                                                   "[pass=пароль | token=токен | key=ключ]."})
                volumes.append(spec)
                continue
            values.setdefault(key.lower(), value.strip())

    for key, title in (("label", "название"), ("icon", "иконка"), ("path", "адрес")):
        if not values.get(key):
            raise ValidationError({"body": f"В файле приложения нет строки «{key}» ({title})."})
    if len(values["label"]) > 64:
        raise ValidationError({"body": "Название длиннее 64 знаков."})
    from desktop.icons import NAMES

    if values["icon"].lower() not in NAMES:
        raise ValidationError({"body": f"Иконки «{values['icon']}» нет в каталоге: {', '.join(NAMES)}."})
    try:
        order = int(values.get("order") or 0)
    except ValueError:
        raise ValidationError({"body": "Порядок «order» это число."})

    try:
        validate_internal_path(values["path"])
    except ValidationError as error:
        raise ValidationError({"body": error.message_dict["path"]})
    return AppSpec(values["label"], values["icon"].lower(), normalize_suffix(values.get("suffix")), values["path"], order, tuple(volumes))


def render(label, icon, path, suffix="", order=0, volumes=()):
    """Текст файла приложения (volumes: готовые строки после слова volume)."""
    lines = [f"label {label}", f"icon {icon}", f"path {path}", *(f"volume {line}" for line in volumes)]
    if suffix:
        lines.append(f"suffix {normalize_suffix(suffix)}")
    if order:
        lines.append(f"order {order}")
    return "\n".join(lines) + "\n"
