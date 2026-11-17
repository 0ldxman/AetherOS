"""Виды нод сценария. Нода в документе: {"id", "type", "x", "y", "data": {поле: значение}}; провод: {"id", "from", "out",
"to", "in"}. Провод потока идёт из выхода в вход "in" (или i1, i2… у «Все из» и «Первое из»); провод-ссылка идёт из выхода
"ref" существительного во вход "f:<поле>" действия: поле берёт значение вещи.

Группы: noun — существительные (вещь мира и её события; нода без входящего провода — старт, со входящим — ожидание), flow — ход,
action — действия движка (engine/actions.py), service — служебные.
"""
import fnmatch
from dataclasses import dataclass, field, replace

from engine.actions import Field

ENTITY, NOUN, FLOW, DATA, ACTION, STRUCT, SERVICE = "entity", "noun", "flow", "data", "action", "struct", "service"
HAPPEN = "happen"                   # события: триггеры, которые игрок руками вызвать не может (время, сигнал, сценарий, автор)
NOUNS = (NOUN, HAPPEN)              # и то и другое — существительные: старт без провода, ожидание со входом
ATTR = "attr"                       # атрибуты: одна сторона сущности (её состояние, время, доступ) — читаются, как сущности
GROUPS = {ENTITY: "Сущности", ATTR: "Атрибуты", NOUN: "Триггеры", HAPPEN: "События", FLOW: "Поток", DATA: "Данные", ACTION: "Действия", STRUCT: "Сценарии и группы", SERVICE: "Служебные"}

# Типы сокетов. event — «случилось» (по нему идёт ход), остальное — данные: читаются в момент, когда нода выполняется.
EVENT = "event"
TYPES = ("event", "bool", "text", "number", "item", "placement", "layer", "machine", "account", "server", "character", "section", "moment", "player", "flag",
         "world_flag", "counter", "offer", "session", "datetime", "volume", "mount", "message", "os")
TYPE_LABELS = {"event": "событие", "bool": "да/нет", "text": "текст", "number": "число", "item": "объект", "placement": "размещение", "layer": "слой", "machine": "машину", "account": "учётку",
               "server": "сетевой ресурс", "character": "персонажа", "section": "раздел", "moment": "момент", "player": "игрока",
               "flag": "метку игрока", "world_flag": "метку мира", "counter": "счётчик", "offer": "возможность", "session": "сессию",
               "datetime": "дату и время", "volume": "диск", "mount": "диск машины", "message": "сообщение",
               "os": "операционную систему"}
THINGS = ("item", "placement", "layer", "machine", "account", "server", "character", "section", "moment", "player", "flag", "world_flag", "counter", "offer",
          "session", "volume", "mount", "os")

# списки: «list:<тип элемента>»; «list:any» — вход, которому подходит любой список (количество)
ELEMENTS = {"text": "Текст", "number": "Число", "bool": "Да/нет", "item": "Объект", "placement": "Размещение", "layer": "Слой", "machine": "Машина", "account": "Учётка", "server": "Сетевой ресурс",
            "character": "Персонаж", "section": "Раздел", "moment": "Момент", "player": "Игрок", "offer": "Возможность", "session": "Сессия",
            "datetime": "Дата и время", "volume": "Диск", "mount": "Диск машины", "os": "Операционная система"}
LIST, ANY_LIST = "list:", "list:any"
TYPES = TYPES + tuple(LIST + name for name in ELEMENTS) + (ANY_LIST,)
TYPE_LABELS.update({LIST + name: f"список ({label.lower()})" for name, label in ELEMENTS.items()})
TYPE_LABELS[ANY_LIST] = "список"
ELEMENT, OF_LIST = "@T", "@list"           # тип входа или выхода ноды списка: элемент или список того, что выбрано в «Тип элементов»


# кратность и несколько типов: «many:<тип>» — одно значение или список; «a|b» — подходит любой из типов
MANY = "many:"


def is_list(kind):
    return str(kind or "").startswith(LIST)


def is_many(kind):
    return str(kind or "").startswith(MANY)


def split_type(kind):
    """(кратность one | list | many, типы) из строки типа: «many:machine|server» -> ("many", ("machine", "server"))."""
    kind = str(kind or "")
    for prefix, mult in ((LIST, "list"), (MANY, "many")):
        if kind.startswith(prefix):
            return mult, tuple(kind[len(prefix):].split("|"))
    return "one", tuple(kind.split("|"))


def type_label(kind):
    """Тип словами (винительный падеж: «ждёт …»): «размещение или список (размещение)», «машину или сервер»."""
    if kind in TYPE_LABELS:
        return TYPE_LABELS[kind]
    mult, bases = split_type(kind)
    one = " или ".join(TYPE_LABELS.get(b, b) for b in bases)
    elements = " или ".join(ELEMENTS.get(b, b).lower() for b in bases)
    return {"one": one, "list": f"список ({elements})", "many": f"{one} или список ({elements})"}[mult]
FIELD_TYPES = {"text": "text", "textarea": "text", "path": "text", "clock": "text", "expr": "text", "scene": "text", "station": "text",
               "graph": "text", "number": "number", "bool": "bool", "condition": "bool", "key": "item", "item": "item", "letter": "item",
               "object": "item", "character": "character", "section": "section", "flag": "flag", "world_flag": "world_flag",
               "counter": "counter", "moment": "moment", "machine": "machine", "system": "os", "time_zone": "text", "server": "server", "player": "player", "layer": "layer", "placement": "placement", "account": "account", "offer": "offer",
               "recipient": "many:character|text", "mail_ref": "item|placement", "attachment": "many:item|placement",
               "offer_group": "many:offer|text", "session": "session", "datetime": "datetime|text", "volume": "volume", "mount": "mount",
               "message": "message"}      # вид поля -> тип его входа; нет в списке — параметр без входа


def field_type(field):
    if field.kind in (ELEMENT, OF_LIST, MANY + ELEMENT):
        return field.kind
    if is_many(field.kind) or "|" in field.kind:    # «одно или список» и несколько типов: вход тех же видов
        prefix, kinds = (MANY, field.kind[len(MANY):]) if is_many(field.kind) else ("", field.kind)
        return prefix + "|".join(FIELD_TYPES.get(b, b) for b in kinds.split("|"))
    if field.kind == "@any":
        return ANY_LIST
    return FIELD_TYPES.get(field.kind, "")


def compatible(src, dst):
    """Можно ли вести провод из выхода типа src во вход типа dst (как в Blender: число в текст можно, событие в данные нельзя).
    Одно значение подходит в список (станет списком из одного), список — в текст (через запятую) и в «любой список».
    «Одно или список» принимает и то и другое; во вход нескольких типов подходит любой из них."""
    if src == dst:
        return True
    bases = split_type(dst)[1]
    if EVENT in bases and len(bases) > 1:                # вход потока, которому подходит и значение («Когда»: событие или условие)
        return src == EVENT or compatible(src, "|".join(b for b in bases if b != EVENT))
    if EVENT in (src, dst):
        return False
    if dst == ANY_LIST:
        return is_list(src) or is_many(src)
    (src_mult, src_bases), (dst_mult, dst_bases) = split_type(src), split_type(dst)
    if src_mult == "list" and dst_mult == "one":
        return dst == "text"
    if len(src_bases) > 1 or len(dst_bases) > 1 or src_mult != "one" or dst_mult != "one":
        return all(any(_one(s, d) for d in dst_bases) for s in src_bases)
    return _one(src, dst)


def _one(src, dst):
    """Совместимость одиночных типов."""
    if src == dst:
        return True
    if dst == "text":
        return True                                  # любое значение подставляется текстом (вещь — своим именем)
    if dst == "number":
        return src == "bool"
    if dst == "bool":
        return src == "number"
    if dst in THINGS:
        return src == "text"                         # вещь по имени
    return False
BOXES = ("group", "scenario")
GLOBAL_EVENTS = frozenset({"world.flag", "world.counter", "moment.started", "moment.ended", "machine.stopped", "machine.started",
                           "machine.maintenance.started", "machine.maintenance.ended"})   # будят всех ждущих            # ноды-обёртки: сокеты берутся из их «Входа» и «Выхода»
SIGNAL_EVENT = "signal"
REF = "ref"
TIMEOUT = "timeout"
TIME_EVENT, MANUAL_EVENT = "@time", "@manual"


@dataclass(frozen=True)
class Sock:
    name: str
    label: str
    type: str = EVENT
    key: str = ""                       # у выхода данных существительного: подробность события (@player — игрок)
    fallback: str = ""                  # если события ещё не было: поле ноды


@dataclass(frozen=True)
class Many:
    """Повторяемые сокеты: число из поля (или длина списка в нём). Имена prefix1, prefix2…; подпись — шаблон с {n} или {label}.
    Пустой prefix: имя берётся из элемента списка (поле name) — так у «Входа» и «Выхода» группы имена не сдвигаются при удалении."""
    side: str
    field: str
    prefix: str
    label: str


@dataclass(frozen=True)
class Grow:
    """Растущий список входов (как подстановки шаблона): строки {"id", "name", "value"} в поле field, вход строки — "f:<id>".
    На ноде всегда есть одна пустая строка; заполнили её (имя, значение или провод) — появляется следующая. single — режимы, где вход один."""
    field: str
    prefix: str
    type: str
    named: bool = False
    min: int = 1
    single: tuple = ()
    needs: str = ""             # поле, где должна быть «{», чтобы появилась пустая строка (у «Текста» — подстановки шаблона)


@dataclass(frozen=True)
class Kind:
    name: str
    label: str
    group: str
    summary: str = ""
    fields: tuple = ()
    outs: tuple = ()
    ins: tuple = ("in",)
    many: tuple = ()
    tail: tuple = ()                    # выходы после повторяемых («Иначе»)
    events: dict = field(default_factory=dict)       # выход -> событие (у существительных)
    match: object = None                # функция(data, out, event) -> bool
    ref: tuple = ()                     # (вид ссылки, поле): что даёт выход ◆
    start_only: bool = False            # только старт (время, вручную)
    subgroup: str = ""
    spec: object = None                 # у действий: engine.actions.Spec
    variants: dict = field(default_factory=dict)     # у действия с выбором: вариант -> (Spec, неизменные поля)
    title: str = ""                     # поле-режим, подпись выбранного варианта — заголовок ноды (как у Math в Blender)
    grow: object = None                 # Grow: растущий список входов
    when: dict = field(default_factory=dict)         # поле -> (поле-режим, значения) или список таких пар: вход есть только в этих режимах
    typed: str = ""                     # поле-параметр «Тип элементов»: им заменяются @T и @list в типах сокетов
    covers: dict = field(default_factory=dict)     # поле -> поля, которые прячутся, когда в него идёт провод (провод их заменяет)
    follows: dict = field(default_factory=dict)    # выход «одно или список» -> поле, чью кратность он повторяет
    titled: dict = field(default_factory=dict)     # поле -> заголовок ноды, когда поле задано (провод или значение)
    infers: dict = field(default_factory=dict)     # поле-провод -> (поле-режим, {тип провода: (значение режима, поле, куда положить значение)})
    hidden: bool = False                # старая нода: работает в готовых сценариях, но в меню её нет
    owned: str = ""                     # нода попытки: вид графа у вещи (graph/owned.py), Tab открывает его
    in_types: dict = field(default_factory=dict)     # вход потока -> тип, если он принимает не только событие («event|bool»)
    inline: dict = field(default_factory=dict)       # поле-вход -> (поле-переключатель в его строке, варианты, которых нет, когда вход задан)
    plural: dict = field(default_factory=dict)       # выход -> (поле-режим, значения): в этих режимах выход — список своего типа
    outs_when: dict = field(default_factory=dict)    # выход данных -> (поле-режим, значения): выход есть только в этих режимах
    types_from: tuple = ()      # входы (или "@rows" — строки растущего списка), чей тип провода Студия пишет в typed


KINDS = {}
DATA_OUTS = {}


def register(kind):
    KINDS[kind.name] = kind
    return kind


def _glob(value, pattern, fold=False):
    if not pattern:
        return True
    value, pattern = str(value or ""), str(pattern)
    if fold:
        value, pattern = value.casefold(), pattern.casefold()
    return fnmatch.fnmatchcase(value, pattern) if any(ch in pattern for ch in "*?[") else value == pattern


def _same(a, b):
    return str(a or "").strip().lower() == str(b or "").strip().lower()


def moved_paths(data):
    """Где файл был и где он теперь: перенос и возврат — from → path, удаление в корзину — path → to, остальное — path."""
    data = data or {}
    path = data.get("path") or ""
    return {"before": data.get("from") or path, "after": data.get("to") or path} if path else {}


def same_placement(event, path, wanted):
    """Событие случилось с размещением wanted («игрок@машина:/путь»)? Мир общий: файл один на всех, поэтому «игрок@» в ключе
    не сужает — изменение любого игрока считается."""
    head, _, want_path = str(wanted or "").strip().partition(":")
    host = head.rpartition("@")[2]
    return bool(path) and want_path == path and _same(host, event.host)


# ---------- существительные ----------

START_FIELDS = (
    Field("repeat", "Запускать", "select", "", False, (("once", "один раз на игрока"), ("game", "один раз за игру"), ("end", "снова после конца"),
                                                       ("always", "каждый раз"))),
)
WAIT_FIELDS = (
    Field("past", "Засчитать, если уже было", "bool"),
    Field("own", "Ждать от", "switch", "", False, (("any", "Любого"), ("player", "Инициатора"), ("item", "Элемента"))),
    Field("timeout", "Таймаут, мин (игровые)", "number", "без таймаута"),
)


def _signal(data, out, event):
    return _same((event.data or {}).get("signal"), data.get("name"))


register(Kind("manual", "Запуск вручную", NOUN, "{label}", (Field("label", "Подпись кнопки", "text", "Запустить"),),
              (Sock("fire", "Запустили"),), events={"fire": MANUAL_EVENT}, start_only=True))
register(Kind("signal", "Сигнал", NOUN, "{name}", (Field("name", "Сигнал", "text", "bunker-open", True),),
              (Sock("got", "Пришёл"),), events={"got": SIGNAL_EVENT}, match=_signal))


# ---------- когда: события по пространствам («Машина: Статус изменён») ----------

def _thing(value, wanted):
    return not wanted or _same(value, wanted)


def same_layer(event, path, d, wanted):
    """Слой события — wanted: «…#c2» — этот слой, без «#» — любой слой этого размещения."""
    head, mark, number = str(wanted or "").rpartition("#")
    if not mark:
        return same_placement(event, path, wanted)
    return same_placement(event, path, head) and str(d.get("id") or "") == number


def match_one(how, value, d, event, wanted):
    if how == "layer":
        return same_layer(event, value, d, wanted)
    if how == "thing":
        return _same(value, wanted)
    if how == "item":
        return _same(d.get("item"), wanted) or _same(d.get("slug"), wanted)
    return same_placement(event, value, wanted)


def _match(**rules):
    """Сравнение события с фильтрами ноды: поле ноды -> (ключ события, как сравнивать). Пустой фильтр пропускает любое."""
    def match(data, out, event):
        d = {**(event.data or {}), "host": event.host, "login": event.login, **moved_paths(event.data)}
        for name, (key, how) in rules.items():
            wanted = data.get(name)
            if wanted in (None, "", []):
                continue
            value = d.get(key, "")
            wants = list(wanted) if isinstance(wanted, (list, tuple)) else [wanted]       # список — подходит любой
            if how in ("thing", "item", "placement", "layer") and len(wants) > 1:
                if not any(match_one(how, value, d, event, one) for one in wants):
                    return False
                continue
            wanted = wants[0]
            if how == "thing" and not _same(value, wanted):
                return False
            if how == "glob" and not _glob(value, wanted, fold=True):
                return False
            if how == "freq":
                try:
                    if abs(float(value or 0) - float(str(wanted).replace(",", "."))) >= 0.0005:
                        return False
                except ValueError:
                    return False
            if how == "item" and not (_same(d.get("item"), wanted) or _same(d.get("slug"), wanted)):
                return False
            if how == "via" and wanted != "any" and value != wanted:
                return False
            if how == "placement" and not same_placement(event, value, wanted):
                return False
            if how == "layer" and not same_layer(event, value, d, wanted):
                return False
            if how == "same" and not _same(value, wanted):
                return False
        return True
    return match


def _when(name, label, fields, outs, events, match, data_outs, summary="", start_only=False, covers=None):
    register(Kind(name, label, NOUN, summary, fields, outs, events=events, match=match, start_only=start_only, covers=covers or {}))
    DATA_OUTS[name] = tuple(data_outs) + (Sock("player", "Игрок", "player", "@player"),)


THINGS_OF = ("character", "machine", "server", "object", "account")
OWNER_WHEN = {"who": ("owner", ("player",)), "character": ("owner", ("character",)), "machine": ("owner", ("machine",)),
              "server": ("owner", ("server",)), "item": ("owner", ("object",)), "account": ("owner", ("account",)), "scope": ("owner", THINGS_OF),
              "for": (("owner", THINGS_OF), ("scope", ("player",)))}
_MACHINE = Field("machine", "Машина", "many:machine", "любая")              # фильтры событий: одно или список — подходит любой
_OBJECT = Field("item", "Объект", "many:object", "любой")
_PATH = Field("path", "Путь", "text", "любой; можно *")
_HOST_OUT = Sock("machine", "Машина", "machine", "host")
_LOGIN_OUT = Sock("login", "Учётка", "account", "account")              # «логин@хост»: свойства — у ноды «Учётка»


_when("on:machine.status", "Машина: Статус изменён", (_MACHINE,),
      (Sock("stopped", "Остановлена"), Sock("started", "Запущена"), Sock("maintenance_on", "Обслуживание началось"),
       Sock("maintenance_off", "Обслуживание кончилось")),
      {"stopped": "machine.stopped", "started": "machine.started", "maintenance_on": "machine.maintenance.started",
       "maintenance_off": "machine.maintenance.ended"}, _match(machine=("host", "thing")), (_HOST_OUT,), "{machine}")
_when("on:terminal.command", "Терминал: Введена команда",
      (_MACHINE, Field("command", "Команда", "text", "любая; можно *"), Field("args", "Аргументы", "text", "любые; можно *")),
      (Sock("run", "Введена"),), {"run": "command.run"}, _match(machine=("host", "thing"), command=("command", "glob"), args=("args", "glob")),
      (_HOST_OUT, _LOGIN_OUT, Sock("command", "Команда", "text", "command"), Sock("args", "Аргументы", "text", "args")), "{command} {args}")
_PLACE_OUTS = (Sock("placement", "Размещение", "placement", "placement"), _LOGIN_OUT)       # объект, путь, машина — у ноды «Размещение»
_GOT_MATCH = _match(item=("item", "item"), via=("via", "via"), path=("path", "glob"), machine=("host", "thing"))


def _got(data, out, event):                     # выданное сценарием или автором — не дело рук игрока: сценарий и так знает, что выдал
    return (event.data or {}).get("via") != "scenario" and _GOT_MATCH(data, out, event)


_when("on:object.got", "Объект: Получен",
      (_OBJECT, Field("via", "Откуда", "select", "", False, (("any", "любым путём"), ("archive", "из письма или архива"), ("forum", "с форума"),
                                                             ("net", "скачан с сервера"), ("xfer", "перенесён с машины"), ("join", "собран из частей"),
                                                             ("key", "ключ в секретах"))),
       _PATH, _MACHINE),
      (Sock("got", "Получен"),), {"got": "object.got"}, _got,
      _PLACE_OUTS + (Sock("via", "Откуда", "text", "via"),), "{item} {via}")

# размещение: что игрок делает с конкретным файлом. Провод «Размещение» — ждать этот файл, иначе фильтры (с объектом — любая его копия).
# Изменение — «было там, стало здесь»: удаление переносит в корзину, возврат — из неё; фильтры смотрят, где файл был.
_PLACE_IN = Field("placement", "Размещение", "many:placement", "любое")
_PLACE_COVERS = {"placement": ("item", "path", "machine")}
_PLACE_MATCH = _match(placement=("before", "placement"), item=("item", "item"), path=("before", "glob"), machine=("host", "thing"))
_when("on:placement.changed", "Размещение: Изменено", (_PLACE_IN, _OBJECT, _PATH, _MACHINE),
      (Sock("edited", "Отредактировано"), Sock("moved", "Перемещено"), Sock("deleted", "Удалено"), Sock("restored", "Восстановлено"),
       Sock("purged", "Удалено насовсем")),
      {"edited": "file.changed", "moved": "file.moved", "deleted": "file.deleted", "restored": "file.restored", "purged": "file.purged"},
      _PLACE_MATCH, (Sock("from_placement", "Было", "placement", "from_placement"),) + _PLACE_OUTS,
      "{item} {path}", covers=_PLACE_COVERS)
_when("on:placement.opened", "Размещение: Открыто", (_PLACE_IN, _OBJECT, _PATH, _MACHINE), (Sock("opened", "Открыл"),), {"opened": "file.read"},
      _PLACE_MATCH, _PLACE_OUTS, "{item} {path}", covers=_PLACE_COVERS)
_when("on:placement.appeared", "Размещение: Появилось",
      (_PLACE_IN, _OBJECT, Field("via", "Как", "select", "", False, (("any", "любым способом"), ("created", "создан игроком"), ("copied", "скопирован"))),
       _PATH, _MACHINE),
      (Sock("appeared", "Появилось"),), {"appeared": "file.created"},
      _match(placement=("path", "placement"), item=("item", "item"), via=("via", "via"), path=("path", "glob"), machine=("host", "thing")),
      _PLACE_OUTS + (Sock("from_placement", "Источник", "placement", "from_placement"), Sock("via", "Как", "text", "via")), "{item} {path}",
      covers=_PLACE_COVERS)
def _layer_types_any():
    from filesystem.layers.registry import registry

    return (("", "любой"),) + tuple((name, name) for name in registry.names())


# слой: что случилось со слоем файла игрока. Провод «Слой» — этот слой, «Размещение» — любой слой этого файла
_when("on:layer.changed", "Слой: Изменён",
      (Field("layer", "Слой", "many:layer|placement", "любой"), _OBJECT, Field("type", "Тип", "select", "", False, _layer_types_any())),
      (Sock("removed", "Снят"), Sock("attempt", "Неверная попытка"), Sock("failed", "Попытки кончились")),
      {"removed": "layer.removed", "attempt": "layer.attempt", "failed": "layer.failed"},
      _match(layer=("path", "layer"), item=("item", "item"), type=("layer", "same")),
      (Sock("layer", "Слой", "layer", "layer_key"), _LOGIN_OUT, Sock("given", "Ввод игрока", "text", "given")),        # остальное — у «Слоя» и «Размещения»
      "{type} {item}", covers={"layer": ("item",)})
_when("on:layer.added", "Слой: Добавлен",
      (Field("layer", "Слой", "many:layer|placement", "любой"), _OBJECT, Field("type", "Тип", "select", "", False, _layer_types_any())),
      (Sock("added", "Добавлен"),), {"added": "layer.added"},
      _match(layer=("path", "layer"), item=("item", "item"), type=("layer", "same")),
      (Sock("layer", "Слой", "layer", "layer_key"), _LOGIN_OUT), "{type} {item}", covers={"layer": ("item",)})


def _mail(data, out, event):
    return (event.data or {}).get("channel") == "mail" and _match(character=("character", "thing"), text=("text", "glob"))(data, out, event)


_WROTE_MATCH = _match(character=("character", "thing"), text=("text", "glob"))


def _wrote(data, out, event):
    channel = data.get("channel") or "any"
    return (channel == "any" or (event.data or {}).get("channel") == channel) and _WROTE_MATCH(data, out, event)


_when("on:character.wrote", "Персонаж: Получил сообщение",
      (Field("channel", "Канал", "switch", "", False, (("any", "Любой"), ("mail", "Почта"), ("forum", "Форум"), ("air", "Эфир"))),
       Field("character", "Персонаж", "many:character", "любой"), Field("text", "Текст", "text", "любой; можно *")),
      (Sock("sent", "Получил"),), {"sent": "character.wrote"}, _wrote,
      (Sock("character", "Персонаж", "character", "character"), Sock("channel", "Канал", "text", "channel"),
       Sock("subject", "Тема", "text", "subject"), Sock("sender", "Подпись", "text", "sender"), Sock("from_address", "Адрес", "text", "sender"),
       Sock("nick", "Ник", "text", "sender"), Sock("freq", "Частота", "text", "freq"), Sock("callsign", "Позывной", "text", "sender"),
       Sock("text", "Текст", "text", "text"), Sock("message", "Сообщение", "message", "message")),
      "{character}")
# подпись игрока в канале: обратный адрес письма, ник на форуме, позывной в эфире; у «Любого» — общая «Подпись»
KINDS["on:character.wrote"] = replace(KINDS["on:character.wrote"], outs_when={
    "subject": ("channel", ("any", "mail", "forum")), "sender": ("channel", ("any",)), "from_address": ("channel", ("mail",)),
    "nick": ("channel", ("forum",)), "freq": ("channel", ("air",)), "callsign": ("channel", ("air",))})
_when("on:character.mail", "Персонаж: Получил письмо", (Field("character", "Персонаж", "many:character", "любой"), Field("text", "Текст", "text", "любой; можно *")),
      (Sock("sent", "Получил"),), {"sent": "character.wrote"}, _mail,
      (Sock("character", "Персонаж", "character", "character"), Sock("text", "Текст", "text", "text")), "{character}")
_AIR_MATCH = _match(freq=("freq", "freq"), text=("text", "glob"), character=("character", "thing"))


def _air(by):
    return lambda data, out, event: (event.data or {}).get("by", "player") == by and _AIR_MATCH(data, out, event)


_AIR_FIELDS = (Field("freq", "Частота, МГц", "text", "любая"), Field("text", "Текст", "text", "любой; можно *"))
_AIR_OUTS = (Sock("freq", "Частота", "text", "freq"), Sock("text", "Текст", "text", "text"), Sock("callsign", "Позывной", "text", "callsign"))
_when("on:air.sent", "Эфир: Передача на частоте", _AIR_FIELDS, (Sock("sent", "Передача"),), {"sent": "air.sent"}, _air("player"), _AIR_OUTS, "{freq}")
_when("on:air.station", "Эфир: Передача станции", _AIR_FIELDS + (Field("character", "Персонаж", "many:character", "любой"),),
      (Sock("sent", "Передача"),), {"sent": "air.sent"}, _air("station"), _AIR_OUTS + (Sock("character", "Персонаж", "character", "character"),),
      "{freq}")
KINDS["on:character.mail"] = replace(KINDS["on:character.mail"], hidden=True)          # теперь «Персонаж: Получил сообщение»
_when("on:moment.status", "Момент: Статус изменён", (Field("moment", "Момент", "many:moment", "любой"),),
      (Sock("started", "Начался"), Sock("ended", "Кончился")), {"started": "moment.started", "ended": "moment.ended"},
      _match(moment=("moment", "thing")), (Sock("moment", "Момент", "moment", "moment"),), "{moment}")


def _value(data, event):
    """Тег или счётчик события тот же, что выбран в ноде: владелец, вещь, чьё (общее или для игрока «для игрока»), имя."""
    d = event.data or {}
    data = owner_defaults(data)
    owner = data.get("owner") or "world"
    if d.get("owner") != owner or not _same(d.get("key"), data.get("name")):
        return False
    thing = data.get({"character": "character", "machine": "machine", "server": "server", "object": "item", "player": "who"}.get(owner, ""), "")
    things = [t for t in (thing if isinstance(thing, (list, tuple)) else [thing]) if t not in (None, "")]
    if owner != "world" and things and not any(_same(d.get("thing"), t) for t in things):
        return False
    if owner not in ("world", "player"):
        if bool(d.get("per")) != (data.get("scope") == "player"):
            return False
        wanted = data.get("for")
        if d.get("per") and wanted not in (None, "") and not _same(getattr(event.user, "username", ""), wanted):
            return False
    return True


def _tag(data, out, event):
    return _value(data, event) and bool((event.data or {}).get("on")) == (out == "set")


def _count(data, out, event):
    return _value(data, event)


def _threshold(data, out, event):
    if not _value(data, event):
        return False
    d = event.data or {}
    try:
        limit, value, delta = int(data.get("threshold") or 0), int(d.get("value") or 0), int(d.get("delta") or 0)
    except (TypeError, ValueError):
        return False
    before = value - delta
    return value >= limit > before if out == "up" else before >= limit > value


def _owner_fields():
    from engine.actions import OWNER_FIELDS

    return tuple(OWNER_FIELDS) + (Field("name", "Имя", "text", "", True),)


def _value_when(name, label, outs, events, match, data_outs, extra=()):
    _when(name, label, _owner_fields() + tuple(extra), outs, events, match, data_outs, "{owner} {name}")
    KINDS[name] = replace(KINDS[name], when=OWNER_WHEN)


_value_when("on:tag", "Тег: Изменён", (Sock("set", "Поставлен"), Sock("unset", "Снят")), {"set": "value.tag", "unset": "value.tag"}, _tag, ())
_value_when("on:count", "Счётчик: Изменён", (Sock("changed", "Изменился"),), {"changed": "value.count"}, _count,
            (Sock("value", "Значение", "number", "value"), Sock("delta", "Разница", "number", "delta")))
_value_when("on:count.threshold", "Счётчик: Порог", (Sock("up", "Дошёл"), Sock("down", "Ушёл ниже")), {"up": "value.count", "down": "value.count"},
            _threshold, (Sock("value", "Значение", "number", "value"),), (Field("threshold", "Порог", "number", "", True),))
_when("on:time", "Время: В момент",
      (Field("at", "Дата и время (игровые)", "datetime", "2031-05-14 21:00", True),),
      (Sock("fire", "Наступило"),), {"fire": TIME_EVENT}, None, (), "{at}", start_only=True)
_when("on:schedule", "Время: По расписанию",
      (Field("mode", "Как часто", "select", "", False, (("daily", "каждый день"), ("weekly", "по дням недели"), ("every", "каждые N минут"))),
       Field("at", "Время (игровое, ЧЧ:ММ)", "clock", "21:00"), Field("days", "Дни недели", "text", "пн, ср, пт"),
       Field("minutes", "Каждые, мин (игровые)", "number", "60")),
      (Sock("fire", "Наступило"),), {"fire": TIME_EVENT}, None, (), "{mode} {at}", start_only=True)
KINDS["on:schedule"] = replace(KINDS["on:schedule"], title="mode", when={"at": ("mode", ("daily", "weekly")), "days": ("mode", ("weekly",)),
                                                                          "minutes": ("mode", ("every",))})


# ---------- попытки: граф у вещи (graph/owned.py) ----------

_when("attempt:machine", "Попытка", (), (Sock("go", "Попытка"),), {"go": "@attempt"}, None,
      (_HOST_OUT, _LOGIN_OUT, Sock("via", "Откуда", "text", "via")), start_only=True)
KINDS["attempt:machine"] = replace(KINDS["attempt:machine"], ins=(), hidden=True)
def _owned_match(kind_name):
    def match(data, out, event):
        from graph import owned

        d = event.data or {}
        if event.name != OWNED_OUT or d.get("socket") != out:
            return False
        return d.get("owner") == owned.owner_of(kind_name, data.get(KINDS[f"try:{kind_name}"].fields[0].name))
    return match


register(Kind("try:machine", "Машина: Попытка входа", NOUN, "{machine}", (Field("machine", "Машина", "machine", "", True),), (),
              match=_owned_match("machine"), owned="machine"))
DATA_OUTS["try:machine"] = ()
_SERVER_OUTS = (Sock("server", "Сетевой ресурс", "server", "address"), Sock("path", "Путь", "text", "path"), _HOST_OUT, _LOGIN_OUT)
_when("attempt:server", "Попытка", (), (Sock("go", "Попытка"),), {"go": "@attempt"}, None, _SERVER_OUTS, start_only=True)
KINDS["attempt:server"] = replace(KINDS["attempt:server"], ins=(), hidden=True)
for _kind, _label in (("net.request", "Сетевой ресурс: Попытка запроса"), ("net.download", "Сетевой ресурс: Попытка скачивания")):
    register(Kind(f"try:{_kind}", _label, NOUN, "{server}", (Field("server", "Сетевой ресурс", "server", "", True),), (),
                  match=_owned_match(_kind), owned=_kind))
    DATA_OUTS[f"try:{_kind}"] = ()


# ---------- ход ----------

register(Kind("wait", "Ждать", FLOW, "{mode}",
              (Field("mode", "Чего ждать", "select", "", False, (("delay", "время"), ("until", "до времени"), ("condition", "пока условие"))),
               Field("minutes", "Минут", "number", "5"), Field("at", "До (игровое)", "datetime", "21:00 или 2031-05-14 21:00"),
               Field("condition", "Условие", "condition"), Field("timeout", "Таймаут, мин", "number", "без таймаута"),
               Field("real", "Реальное время вместо игрового", "bool")),
              (Sock("next", "Дальше"), Sock(TIMEOUT, "Таймаут"))))
register(Kind("check", "Направить: Если", FLOW, "{condition}", (Field("condition", "Условие", "condition", "", True),),
              (Sock("yes", "Истина"), Sock("no", "Ложь"))))
register(Kind("choose", "Выбор", FLOW, "", (Field("rows", "Если", "rows"),),
              many=(Many("out", "rows", "r", "{label}"),), tail=(Sock("else", "Иначе"),), hidden=True))      # старое: теперь цепочка «Если»
register(Kind("random", "Направить: Случайно", FLOW, "", (Field("branches", "Веса веток", "weights"),),
              many=(Many("out", "branches", "b", "Ветка {n}"),)))
register(Kind("turns", "Направить: По очереди", FLOW, "{count}", (
    Field("count", "Сколько веток", "number", "2"),
    Field("cycle", "После последней", "switch", "", False, (("repeat", "Снова с первой"), ("stop", "В «Закончились»")))),
              many=(Many("out", "count", "b", "Ветка {n}"),), tail=(Sock("over", "Закончились"),), when={"over": ("cycle", ("stop",))}))
register(Kind("first", "Первые в мире", FLOW, "первые {count}", (Field("count", "Сколько первых", "number", "1"),),
              (Sock("pass", "Успел"), Sock("late", "Опоздал"))))
register(Kind("once", "Однажды", FLOW, "{per}", (Field("per", "Для кого", "select", "", False, (("game", "за игру"), ("player", "на каждого игрока"))),),
              (Sock("pass", "Впервые"), Sock("again", "Уже было"))))
register(Kind("all", "Ожидание: Все", FLOW, "{count}", (Field("count", "Сколько входов", "number", "2"),),
              (Sock("next", "Дальше"),), ins=(), many=(Many("in", "count", "i", "Вход {n}"),)))
register(Kind("race", "Ожидание: Любой", FLOW, "{count}", (Field("count", "Сколько входов", "number", "2"),),
              ins=(), many=(Many("in", "count", "i", "Вход {n}"), Many("out", "count", "o", "Первым вход {n}"))))
register(Kind("some", "Ожидание: По количеству", FLOW, "{need} из {count}", (Field("count", "Сколько входов", "number", "3"),
                                                                              Field("need", "Сколько нужно", "number", "2")),
              (Sock("next", "Дальше"),), ins=(), many=(Many("in", "count", "i", "Вход {n}"),)))
register(Kind("end", "Конец", FLOW, "{outcome}",
              (Field("outcome", "Исход", "select", "", False, (("passed", "прошёл"), ("failed", "провалил"), ("aborted", "прервано"))),)))
register(Kind("each", "Для каждого", FLOW, "{mode}", (
    Field("of", "Тип элементов", "hidden", "", False, tuple(ELEMENTS.items())), Field("list", "Список", OF_LIST),
    Field("mode", "Ждать", "switch", "", False, (("all", "Все"), ("first", "Первого"), ("count", "N"))),
    Field("need", "Сколько", "number", "2")), (Sock("done", "Готово"),), typed="of", types_from=("list",), when={"need": ("mode", ("count",))}))
DATA_OUTS["each"] = (Sock("finished", "Успели", OF_LIST), Sock("first", "Первый", ELEMENT))
register(Kind("branch_in", "Начало ветки", FLOW, "", (), (Sock("next", "Поток"),), ins=(), hidden=True))
DATA_OUTS["branch_in"] = (Sock("item", "Элемент", "text"), Sock("index", "Номер", "number"))
register(Kind("branch_out", "Конец ветки", FLOW, "", (), (), hidden=True))
HELP_EACH = {
    "each": "Ветка на каждый элемент списка (Tab — внутрь): от «Начала ветки» до «Конца ветки», внутри можно ждать. Элемент-игрок — инициатор ветки, "
            "элемент-учётка — её место (у триггеров «Ждать от: Элемента» — только события на ней). «Готово» — когда вернулись все, первый или N; "
            "остальные ветки снимаются. Выходы: Успели (по порядку), Первый.",
    "branch_in": "Начало ветки «Для каждого»: Элемент и Номер (с 1).",
    "branch_out": "Конец ветки: элемент вернулся — засчитан в «Успели».",
}
register(Kind("foreach", "Для каждого (старое)", FLOW, "", (Field("of", "Тип элементов", "hidden", "", False, tuple(ELEMENTS.items())),
                                                    Field("list", "Список", OF_LIST)),
              (Sock("each", "Каждый"), Sock("done", "Готово")), typed="of", types_from=("list",), hidden=True))
register(Kind("answer", "Ответить", FLOW, "{mode}",
              (Field("mode", "Ответ", "select", "", False, (("allow", "впустить"), ("deny", "отказать"), ("block", "заблокировать"), ("default", "как обычно (пароль, ключи, токен)"))),
               Field("text", "Текст отказа", "text", "node unavailable"), Field("minutes", "Блокировка, мин", "number", "10")),
              (Sock("next", "Дальше"), Sock("allowed", "Пустили"), Sock("refused", "Отказали")),
              match=lambda data, out, event: (not data.get("_host") or _same(event.host, data["_host"]))
              and (not data.get("_login") or _same(event.login, data["_login"])),
              when={"text": ("mode", ("deny", "block")), "minutes": ("mode", ("block",)), "allowed": ("mode", ("default",)),
                    "refused": ("mode", ("default",))}))
register(Kind("reroute", "Перенаправление", SERVICE, "", (), (Sock("next", ""),)))


# ---------- сценарии и группы ----------

register(Kind("group", "Группа", STRUCT, "{title}", (Field("group", "Группа", "hidden"),), ins=()))
register(Kind("group_in", "Вход", STRUCT, "", (Field("sockets", "Входы", "sockets"),), ins=(), many=(Many("out", "sockets", "", "{label}"),)))
register(Kind("group_out", "Выход", STRUCT, "", (Field("sockets", "Выходы", "sockets"),), ins=(), many=(Many("in", "sockets", "", "{label}"),)))
register(Kind("scenario", "Сценарий", STRUCT, "{graph}", (Field("graph", "Сценарий", "graph", "", True),), ins=()))
register(Kind("launch", "Запустить сценарий", STRUCT, "{graph}",
              (Field("graph", "Сценарий", "graph", "", True), Field("socket", "Вход сценария", "text", "первый")),
              (Sock("next", "Дальше"), Sock("fail", "Не вышло"))))
register(Kind("send_signal", "Послать сигнал", STRUCT, "{name} → {to}",
              (Field("name", "Сигнал", "text", "bunker-open", True),
               Field("to", "Кому", "select", "", False, (("player", "этому игроку"), ("all", "всем")))),
              (Sock("next", "Дальше"),)))


# ---------- служебные ----------

register(Kind("stage", "Этап", SERVICE, "{title}", (Field("title", "Этап", "text", "нашёл архив", True),), (Sock("next", "Дальше"),)))
register(Kind("note", "Заметка", SERVICE, "", (Field("text", "Текст", "textarea"),), ins=()))
register(Kind("frame", "Рамка", SERVICE, "{title}", (Field("title", "Подпись", "text"),), ins=()))


# ---------- действия: из словаря движка ----------

REF_KINDS = {"item": "item", "key": "item", "letter": "item", "character": "character", "section": "section", "flag": "flag",
             "world_flag": "world_flag", "counter": "counter"}      # вид поля действия -> вид ссылки, которую оно принимает


ACTION_WHEN = {"tag": OWNER_WHEN, "count": {**OWNER_WHEN, "delta": ("mode", ("add",)), "value": ("mode", ("set",))}}
REPLACED = {"kick", "air"}                  # «Сессия: Закрыть», «Персонаж: Написать»
HIDDEN_CHOICES = {"mail", "forum"}          # «Персонаж: Написать»
LEGACY = {"flag", "unflag", "world_flag", "world_unflag", "world_count", "player_count", "character_tag"}   # теперь «Тег» и «Счётчик»


# действия по пространствам, как у «Когда»: одно действие движка — подпись; несколько — нода с выбором, заголовок по выбору
RENAMED = {
    "net_node": "Сетевой ресурс: Изменить узел", "file_delete": "Объект: Удалить у игрока", "kick": "Игрок: Выбросить из сессии (старое)",
    "notify": "Экран: Уведомление", "ticker": "Экран: Бегущая строка", "windows": "Экран: Окна ошибок", "open_window": "Экран: Окно с адресом",
    "blackout": "Экран: Чёрный экран", "scene": "Экран: Сцена", "air": "Персонаж: Передать в эфир", "news": "Новости: Опубликовать",
}
_OWNER = ("owner", "who", "character", "machine", "server", "item", "account", "scope", "for", "name")
CHOICES = (
    ("machine.status", "Машина: Изменить статус", (("stop", "Остановить", "machine_power", {"state": "stop"}, ("host",)),
                                                   ("start", "Запустить", "machine_power", {"state": "start"}, ("host",)),
                                                   ("maintenance", "Обслуживание", "machine_power", {"state": "maintenance"}, ("host", "text")),
                                                   ("reboot", "Перезагрузить", "machine_power", {"state": "reboot"}, ("host", "minutes")))),
    ("terminal", "Терминал: Вывести", (("text", "Текст", "terminal_text", {}, ("text",)), ("scene", "Сцена", "terminal_scene", {}, ("scene",)))),
    ("mail", "Персонаж: Отправить письмо", (("player", "Отправить письмо игроку", "letter", {}, ("to", "item", "delay")),
                                            ("all", "Отправить письмо всем", "letter_all", {}, ("item", "machines", "systems")))),
    ("forum", "Персонаж: Написать на форум", (("new", "Новая тема", "forum", {"mode": "new"}, ("section", "character", "title", "text")),
                                  ("append", "Ответ в тему", "forum", {"mode": "append"}, ("section", "character", "title", "text")))),
    ("screen", "Экран: Показать", (("notify", "Уведомление", "notify", {}, ("title", "text")),
                                   ("ticker", "Бегущая строка", "ticker", {}, ("text", "seconds")),
                                   ("windows", "Окна ошибок", "windows", {}, ("message", "count", "gap")),
                                   ("open_window", "Окно с адресом", "open_window", {}, ("url", "title")),
                                   ("blackout", "Чёрный экран", "blackout", {}, ("title", "text", "tone", "hold")),
                                   ("scene", "Сцена", "scene", {}, ("scene",)))),
    ("moment", "Момент: Изменить статус", (("start", "Начать", "moment_start", {}, ("moment",)), ("end", "Закончить", "moment_end", {}, ("moment",)))),
    ("tag", "Тег: Изменить", (("on", "Поставить", "tag", {"mode": "on"}, _OWNER), ("off", "Снять", "tag", {"mode": "off"}, _OWNER))),
    ("count", "Счётчик: Изменить", (("add", "Прибавить", "count", {"mode": "add"}, _OWNER + ("delta",)),
                                    ("set", "Задать", "count", {"mode": "set"}, _OWNER + ("value",)))),
)
CHOSEN = {spec for _, _, variants in CHOICES for _, _, spec, _, _ in variants}
FIXED_TITLE = {"forum"}                     # заголовок не меняется по выбору


def _out_on(kind, data, name):
    rule = kind.outs_when.get(name)
    if not rule:
        return True
    chosen = next((f for f in kind.fields if f.name == rule[0]), None)
    return ((data or {}).get(rule[0]) or (chosen.options[0][0] if chosen is not None and chosen.options else "")) in rule[1]


def active(kind, data, name):
    """Вход есть в выбранном режиме (Kind.when), как на холсте: неактивные поля не проверяются и не нужны."""
    rule = kind.when.get(name)
    if not rule:
        return True
    for mode, values in ([rule] if isinstance(rule[0], str) else rule):
        chosen = next((f for f in kind.fields if f.name == mode), None)
        current = data.get(mode) or (chosen.options[0][0] if chosen is not None and chosen.options else "")
        if str(current) not in values:
            return False
    return True


def titled(kind, data):
    """Заголовок ноды с её данными: «Размещение: Удалить в корзину», «Размещение: Добавить»."""
    for name, label in kind.titled.items():
        if (data or {}).get(name) not in (None, ""):
            return label
    if kind.title:
        chosen = next((f for f in kind.fields if f.name == kind.title), None)
        value = (data or {}).get(kind.title) or (chosen.options[0][0] if chosen and chosen.options else "")
        label = dict(chosen.options).get(value, "") if chosen else ""
        space = kind.label.split(": ")[0] if ": " in kind.label else ""
        return f"{space}: {label}" if space and label else label or kind.label
    return kind.label


def action_of(kind, data):
    """(Spec, действие для движка) ноды действия: у ноды с выбором — по варианту, с его неизменными полями."""
    if kind.variants:
        values = [v for v, _ in kind.fields[0].options]
        spec, fixed = kind.variants.get(data.get("variant") or values[0], kind.variants[values[0]])
    else:
        spec, fixed = kind.spec, {}
    action = {"do": spec.name}
    for item in spec.fields:
        value = data.get(item.name)
        if item.name not in fixed and value not in (None, ""):
            action[item.name] = value
    return spec, {**action, **fixed}


def _choice(key, label, variants):
    from engine.actions import REGISTRY

    fields, shown = [], {}
    for value, _, spec_name, fixed, names in variants:
        for item in REGISTRY[spec_name].fields:
            if item.name in names and item.name not in fixed:
                if item.name not in shown:
                    fields.append(item)
                shown.setdefault(item.name, []).append(value)
    when = {}
    for name, modes in shown.items():
        rule = [("variant", tuple(modes))]
        extra = OWNER_WHEN.get(name) if variants[0][2] in ("tag", "count") else None
        if extra:
            rule += list([extra] if isinstance(extra[0], str) else extra)
        when[name] = rule if len(rule) > 1 else rule[0]
    choice = Field("variant", "Действие", "select", "", False, tuple((value, title) for value, title, *_ in variants))
    register(Kind(f"act:{key}", label, ACTION, "", (choice, *fields), (Sock("next", "Сделано"), Sock("fail", "Не вышло")),
                  title="" if key in FIXED_TITLE else "variant", when=when, hidden=key in HIDDEN_CHOICES,
                  variants={value: (REGISTRY[spec_name], fixed) for value, _, spec_name, fixed, _ in variants}))


def _actions():
    from engine.actions import HOST, REGISTRY
    from engine.context import SESSION

    for spec in REGISTRY.values():
        if spec.needs in (HOST, SESSION) or spec.run is None:      # эффекты браузера ждут доставки вне запроса (этап 3)
            continue
        label = RENAMED.get(spec.name, spec.label)
        register(Kind("do:" + spec.name, label, ACTION, spec.summary, spec.fields, (Sock("next", "Сделано"), Sock("fail", "Не вышло")),
                      subgroup="" if ": " in label else spec.group, spec=spec, when=ACTION_WHEN.get(spec.name, {}),
                      hidden=spec.name in LEGACY or spec.name in CHOSEN or spec.name in REPLACED))
    for key, label, variants in CHOICES:
        _choice(key, label, variants)


_actions()
# «Экран: Показать» — кому: инициатору, всем игрокам в игре или указанным (игрок, сессия, учётка, машина — кто сейчас там)
_SCREEN = KINDS["act:screen"]
KINDS["act:screen"] = replace(_SCREEN, fields=_SCREEN.fields[:1] + (
    Field("who", "Кому", "switch", "", False, (("player", "Игрок"), ("list", "Указать"))),
    Field("scope", "", "switch", "", False, (("turn", "Инициатору"), ("all", "Всем игрокам"))),
    Field("targets", "Адресаты", "many:player|session|account|machine", "игрок, сессия, учётка или машина", True),
) + _SCREEN.fields[1:], when={**_SCREEN.when, "scope": ("who", ("player",)), "targets": ("who", ("list",))})

def _layer_type_names():
    from filesystem.layers.registry import registry

    return tuple((name, name) for name in registry.names())


_LAYER_TYPES = _layer_type_names()

# действия с размещением игрока (filesystem/placements.py): на вход одно размещение или список, выход «Размещение» — где файл теперь
_ACT_OUTS = (Sock("next", "Сделано"), Sock("fail", "Не вышло"))
register(Kind("act:placement", "Размещение: Изменить", ACTION, "{placement}", (
    Field("variant", "Действие", "select", "", False, (("move", "Переместить"), ("replace", "Подменить объект"), ("trash", "Удалить в корзину"),
                                                       ("purge", "Удалить насовсем"), ("restore", "Восстановить"),
                                                       ("add_layer", "Добавить слой защиты"), ("reset_layers", "Вернуть слои защиты"))),
    Field("placement", "Размещение", "many:placement", "игрок@машина:/путь", True),
    Field("target", "Новый путь", "path", "/путь, новое имя или папка/"), Field("restore_to", "Куда", "path", "на прежнее место"),
    Field("item", "Новый объект", "object", "", True),
    Field("type", "Тип слоя", "select", "", False, _LAYER_TYPES), Field("args", "Параметры", "text", "как в описании: пароль, кодировка…"),
), _ACT_OUTS, title="variant", when={"target": ("variant", ("move",)), "restore_to": ("variant", ("restore",)), "item": ("variant", ("replace",)),
                                      "type": ("variant", ("add_layer",)), "args": ("variant", ("add_layer",))},
    follows={"placement": "placement"}))
DATA_OUTS["act:placement"] = (Sock("placement", "Размещение", "many:placement"),)
register(Kind("act:placement.create", "Размещение: Создать", ACTION, "{item} {path}", (
    Field("placement", "Куда", "many:placement", "игрок@машина:/путь"), Field("machine", "Машина", "machine"),
    Field("path", "Путь", "path", "/home/{login}/note.txt; ключ — пусто: в секреты"), Field("player", "Игрок", "player", "инициатор"),
    Field("item", "Объект", "object", "нет — свой файл с текстом"), Field("text", "Текст", "textarea", "подстановки {host}, {login}, {path}…"),
), _ACT_OUTS, covers={"placement": ("machine", "path", "player"), "item": ("text",)}, titled={"item": "Размещение: Добавить"},
    follows={"placement": "placement"}))
DATA_OUTS["act:placement.create"] = (Sock("placement", "Размещение", "many:placement"),)
for _old in ("do:file", "do:key", "do:file_delete", "do:file_change", "do:layer_remove", "do:account"):     # теперь «Размещение: …» и «Слой: Изменить»
    KINDS.pop(_old, None)
register(Kind("act:layer", "Слой: Изменить", ACTION, "{layer}", (
    Field("variant", "Действие", "select", "", False, (("remove", "Снять"), ("quiet", "Снять тихо"), ("attempts", "Сбросить попытки"))),
    Field("layer", "Слой", "many:layer|placement", "слой или размещение (его верхний слой)", True),
), _ACT_OUTS, title="variant", follows={"layer": "layer"}))
DATA_OUTS["act:layer"] = (Sock("layer", "Слой", "many:layer"),)
PLACEMENT_ACTS = ("act:placement", "act:placement.create", "act:layer")

# машина и её учётки (machines/world/edits.py)
register(Kind("act:machine.change", "Машина: Изменить", ACTION, "{machine}", (
    Field("variant", "Что изменить", "select", "", False, (("name", "Изменить имя"), ("address", "Изменить адрес"), ("system", "Изменить ОС"),
                                                           ("time_zone", "Изменить часовой пояс"), ("host_key", "Изменить ключ хоста"),
                                                           ("note", "Изменить приветствие"), ("booted", "Изменить «Включена с»"),
                                                           ("display", "Изменить графику"), ("seats", "Изменить число мест"))),
    Field("machine", "Машина", "many:machine", "", True), Field("name", "Имя", "text", "", True), Field("address", "Адрес", "text", "", True),
    Field("system", "ОС", "system", "", True), Field("time_zone", "Часовой пояс", "time_zone", "", True),
    Field("host_key", "Ключ хоста", "text", "пусто — новый случайный"), Field("note", "Приветствие", "textarea", "{note} в приветствии ОС"),
    Field("booted", "Включена с", "datetime", "2031-03-02 14:05 или «сейчас»", True),
    Field("display", "Графика", "switch", "", False, (("on", "Есть"), ("off", "Нет"))),
    Field("seats", "Мест", "number", "пусто — без ограничения"),
), _ACT_OUTS, title="variant",
   when={name: ("variant", (name,)) for name in ("name", "address", "system", "time_zone", "host_key", "note", "booted", "display", "seats")}))
# состояние машины: сколько дефектов у подключения к ней (machines/world/channel.py); (поле, подпись, подсказка, предел)
STATE = (("lag_ms", "Задержка, мс", "0 — нет; 800 — заметно, 3000 — тяжело", None),
         ("noise_pct", "Помехи, % символов", "0 — нет; 1 — изредка, 5 — сильно", 100),
         ("drop_pct", "Обрывы, % в минуту", "0 — нет; 5 — примерно раз в 20 минут", 100),
         ("bandwidth_kbps", "КБ/с", "0 — без ограничения; 50 — медленно", None),
         ("input_noise_pct", "Помехи ввода, %", "0 — нет; 3 — заметно", 100),
         ("overload_pct", "Перегрузка, % команд", "0 — нет; 15 — заметно", 100),
         ("screen_noise", "Помехи изображения", "0–100: 25 — мутно, 50 — половина читается", 100))
register(Kind("act:machine.state", "Машина: Изменить состояние", ACTION, "{machine}", (
    Field("mode", "Как", "switch", "", False, (("set", "Задать"), ("add", "Добавить"), ("reset", "Сбросить"))),
    Field("machine", "Машина", "many:machine", "", True),
    *(Field(name, label, "number", hint) for name, label, hint, _ in STATE),
), _ACT_OUTS, when={name: ("mode", ("set", "add")) for name, *_ in STATE}))
register(Kind("act:account.change", "Учётка: Изменить", ACTION, "{account}", (
    Field("variant", "Действие", "select", "", False, (("mail", "Изменить почту"), ("password", "Изменить пароль"), ("keys", "Установить выражение ключей"),
                                                       ("points_add", "Добавить точки входа"), ("points_remove", "Убрать точки входа"),
                                                       ("groups_add", "Добавить в группы"), ("groups_remove", "Убрать из групп"),
                                                       ("token_add", "Создать токен"), ("token_remove", "Удалить токены"))),
    Field("account", "Учётка", "many:account", "логин@хост", True),
    Field("mail", "Почта", "text", "пусто — логин@метка"), Field("password", "Пароль", "text", "пусто — без пароля"),
    Field("keys", "Выражение ключей", "text", "cardkey and badge; пусто — без ключей"),
    Field("points", "Точки входа", "many:text", "14.230 или 22"), Field("groups", "Группы", "many:text", "ops"),
    Field("uses", "Сколько раз", "number", "без предела"), Field("minutes", "Живёт, мин", "number", "без предела"),
    Field("tokens", "Токены", "many:text", "пусто — все токены учётки"),
), _ACT_OUTS, title="variant", when={"mail": ("variant", ("mail",)), "password": ("variant", ("password",)), "keys": ("variant", ("keys",)),
                                      "points": ("variant", ("points_add", "points_remove")), "groups": ("variant", ("groups_add", "groups_remove")),
                                      "uses": ("variant", ("token_add",)), "minutes": ("variant", ("token_add",)), "tokens": ("variant", ("token_remove",))},
    follows={"token": "account"}))
DATA_OUTS["act:account.change"] = (Sock("token", "Токен", "many:text"),)
register(Kind("act:account.access", "Учётка: Блокировка", ACTION, "{account}", (
    Field("variant", "Действие", "select", "", False, (("block", "Заблокировать учётку"), ("unblock", "Разблокировать учётку"))),
    Field("account", "Учётка", "many:account", "логин@хост", True),
    Field("scope", "Кому", "select", "", False, (("player", "игроку"), ("all", "всем"))), Field("player", "Игрок", "player", "инициатор"),
    Field("minutes", "На сколько, мин", "number", "10"), Field("text", "Текст блокировки", "text", ""),
), _ACT_OUTS, title="variant", when={"player": ("scope", ("player",)), "minutes": ("variant", ("block",)), "text": ("variant", ("block",))}))
register(Kind("act:account.manage", "Учётка: Создать или удалить", ACTION, "{login}{account}", (
    Field("variant", "Действие", "select", "", False, (("create", "Создать учётку"), ("delete", "Удалить учётку"))),
    Field("owner", "Чья", "switch", "", False, (("story", "Сюжетная"), ("player", "Инициатора"))),
    Field("machine", "Машина", "machine", "", True), Field("login", "Логин", "text", "{player} — логин игрока", True), Field("name", "Имя", "text", "как логин"),
    Field("points", "Точки входа", "many:text", "14.230 или 22; пусто — извне не зайти"), Field("password", "Пароль", "text", "без пароля"),
    Field("mail", "Почта", "text", "логин@метка"), Field("groups", "Группы", "many:text", ""),
    Field("account", "Учётка", "many:account", "логин@хост", True),
), _ACT_OUTS, title="variant", when={**{name: ("variant", ("create",)) for name in ("owner", "machine", "login", "name", "points", "password", "mail", "groups")},
                                      "account": ("variant", ("delete",))}))
DATA_OUTS["act:account.manage"] = (Sock("account", "Учётка", "account"),)
register(Kind("act:machine.disk", "Машина: Изменить диск", ACTION, "{point}{mount}", (
    Field("variant", "Действие", "select", "", False, (("attach", "Подключить диск"), ("remote", "Подключить сетевой диск"), ("detach", "Отключить диск"))),
    Field("machine", "Машина", "machine", "", True), Field("volume", "Диск", "volume", "", True), Field("folder", "Папка диска", "path", "весь диск"),
    Field("host", "Хост", "machine", "", True), Field("path", "Путь на хосте", "path", "/srv/archive", True),
    Field("account", "Учётка хоста", "account", "guest"), Field("point", "Точка", "path", "/mnt/archive"),
    Field("read_only", "Только чтение", "bool"), Field("mount", "Диск машины", "mount", "хост:/точка"),
), _ACT_OUTS, title="variant", when={"volume": ("variant", ("attach", "detach")), "folder": ("variant", ("attach",)),
                                      "host": ("variant", ("remote",)), "path": ("variant", ("remote",)), "account": ("variant", ("remote",)),
                                      "read_only": ("variant", ("attach", "remote")), "mount": ("variant", ("detach",))}))
DATA_OUTS["act:machine.disk"] = (Sock("mount", "Диск машины", "mount"),)
MACHINE_ACTS = ("act:machine.change", "act:machine.state", "act:account.change", "act:account.access", "act:account.manage", "act:machine.disk")

# возможности: что сценарий открыл игроку в игре (graph/offers.py; письмо — mail/talk.py)
_MAIL, _TYPED = ("channel", ("mail",)), ("channel", ("mail", "command"))
register(Kind("ent:offer", "Возможность", ENTITY, "{title}{command}", (
    Field("channel", "Канал", "select", "", False, (("mail", "Письмо"), ("command", "Команда терминала"), ("choice", "Окно с выбором"),
                                                     ("file", "Кнопка у файла"))),
    Field("mode", "Как", "switch", "", False, (("new", "Новое"), ("reply", "Ответ"), ("forward", "Пересылка"))),
    Field("letter", "Как", "mail_ref", "любое письмо"),
    Field("to", "Кому", "recipient", "адрес или персонаж"),
    Field("command", "Команда", "text", "unlock", True),
    Field("item", "Объект", "many:object", "любой"), Field("path", "Путь", "text", "любой; можно *"),
    Field("title", "Подпись", "text", "", True), Field("caption", "Надпись у кнопок", "text", "пусто — без надписи"),
    Field("message", "Текст окна", "textarea", ""), Field("buttons", "Кнопки", "many:text", "Да, Нет"),
    Field("text", "Текст для набора", "textarea", "{{секрет}}, [[док: 7|9]]; пусто — без набора"),
    Field("reply_ok", "Ответ, если верно", "text", "ничего"), Field("reply_wrong", "Ответ, если неверно", "text", "{command}: access denied"),
    Field("attach", "Вложение", "attachment", "ничего"),
    Field("group", "Группа", "text", "использована одна — закрыты все"),
), ins=(), when={
    **{name: _MAIL for name in ("mode", "letter", "to", "attach")},
    "text": _TYPED,
    **{name: ("channel", ("command",)) for name in ("command", "reply_ok", "reply_wrong")},
    "title": ("channel", ("mail", "choice", "file")), "message": ("channel", ("choice",)), "buttons": ("channel", ("choice",)),
    **{name: ("channel", ("file",)) for name in ("item", "path", "caption")}}, title="channel", inline={"letter": ("mode", ("new",))}))
DATA_OUTS["ent:offer"] = (Sock("offer", "Возможность", "offer"),)
_OFFER_SCOPE = Field("scope", "Для кого", "switch", "", False, (("player", "Инициатору"), ("account", "Учётке"), ("all", "Всем")))
register(Kind("act:offer", "Возможность: Изменить", ACTION, "{offer}", (
    Field("state", "Состояние", "switch", "", False, (("open", "Открыть"), ("mystery", "Показать «???»"), ("hidden", "Скрыть"))),
    Field("whole", "Что", "switch", "", False, (("one", "Одну"), ("group", "Группу"))),
    Field("offer", "Возможность", "offer_group", "возможность или имя группы", True), _OFFER_SCOPE,
    Field("account", "Учётка", "account", "учётка события"),
), _ACT_OUTS, in_types={"in": "event|bool"}, title="state", inline={"offer": ("whole", ())}, when={"account": ("scope", ("account",))}))
OFFER_ACTS = ("act:offer",)
DATA_OUTS["act:mail"] = (Sock("item", "Письмо", "item"),)        # то же письмо — в «В ответ на» у «Возможности»


USED_OFFER = "on:offer.used"        # выходы-события — по сущности на проводе «Возможность» (graph/offers.used_outs)


def _offer_used(data, out, event):
    d = event.data or {}
    wanted = data.get("offer")
    wants = [str(w).strip() for w in (wanted if isinstance(wanted, (list, tuple)) else [wanted]) if str(w or "").strip()]
    if wants and not any(_same(w, d.get("offer")) for w in wants):
        return False
    return out in (d.get("outs") or [d.get("result")])


_when(USED_OFFER, "Возможность: Использована", (Field("offer", "Возможность", "many:offer", "любая"),),
      (Sock("ok", "Верно"), Sock("wrong", "Неверно")), {"ok": "offer.used", "wrong": "offer.used"}, _offer_used,
      (Sock("offer", "Возможность", "offer", "offer"), Sock("text", "Текст", "text", "text"), Sock("placement", "Размещение", "placement", "placement"),
       Sock("attachment", "Вложение", "placement", "attachment"), _LOGIN_OUT), "{offer}")

# учётка — «логин@хост»
register(Kind("ent:account", "Учётка", ENTITY, "{login}", (
    Field("account", "Учётка", "account", "логин@хост"), Field("machine", "Машина", "machine"), Field("login", "Логин", "text"),
), ins=(), covers={"account": ("machine", "login")}))
DATA_OUTS["ent:account"] = (Sock("value", "Учётка", "account"), Sock("machine", "Машина", "machine"), Sock("login", "Логин", "text"),
                            Sock("name", "Имя", "text"), Sock("mail", "Почта", "text"), Sock("sessions", "Сессии", "list:session"))


# ---------- пояснения (подсказки на холсте, как в Blender) ----------

HELP = {
    "act:placement": "Что-то сделать с файлом игрока: перенести (путь, новое имя или папка/), подменить объект, удалить в корзину или насовсем, "
                     "вернуть из корзины, добавить слой защиты поверх (тип и параметры как в описании), вернуть слои как в описании. "
                     "На вход — одно размещение или список: с каждым. «Размещение» на выходе — где файл теперь.",
    "act:placement.create": "Создать файл игроку: с объектом — «Добавить» (ключ без пути — в папку секретов), без объекта — свой файл с текстом. "
                            "Куда — размещение или Машина + Путь (+ Игрок, пусто — инициатор).",
    "ent:offer": "Что предлагается игроку. Письмо — вариант ответа, нового письма или пересылки: игрок выбирает его в списке и набирает текст "
                 "({{секрет}} знает сам, [[док: 7|9]] выбирает — развилка становится выходом «Использована»). Команда терминала — скрытая "
                 "команда (вместо «command not found»), аргументы сверяются так же. Окно с выбором — на столе игрока. Кнопка у файла — в окне "
                 "файла (объект, путь). Группа: использована одна — скрыты все. Выход — ключ для «Изменить» и «Использована».",
    "act:offer": "Что игрок видит: Открыть — вариант и можно его применить; Показать «???» — знает, что вариант есть, но выбрать нельзя; "
                 "Скрыть — ничего (так по умолчанию). Для кого: инициатору, учётке (видят все, кто на ней, — провод или учётка события; верный ответ одного скрывает вариант у всех на ней) или всем. «Группу» — все возможности группы: имя группы текстом (в этом сценарии) или возможность "
                 "из неё проводом; можно списком. Во «Когда» — событие (состояние держится до следующего "
                 "изменения; «Скрыть» перекрывает условия) или провод условия (пока верно; несколько — побеждает самое открытое; "
                 "только возможности этого сценария).",
    "on:offer.used": "Игрок использовал возможность. Выходы — по подключённой сущности: Верно / Неверно (текст, секрет и вложение), "
                     "кнопки окна, «Нажата» у файла; развилки текста — выходами-словами. Лимит попыток — счётчик по «Неверно».",
    "ent:account": "Учётка на машине: провод «Учётка» (логин@хост) или Машина + Логин. Группы, точки входа, блокировка, ключи и токены — "
                   "в атрибуте «Учётка: Доступ».",
    "attr:account.access": "Доступ учётки сейчас: группы, точки входа, root, ключи (выражение, как в учётке), живые токены. "
                           "«Заблокирована» — для инициатора.",
    "attr:machine.state": "Состояние машины — дефекты подключения к ней: задержка, помехи вывода, обрывы, КБ/с для xfer, помехи ввода, "
                          "перегрузка, помехи изображения стола. «Есть дефекты» — хоть что-то не ноль. Менять — «Машина: Изменить состояние».",
    "attr:machine.time": "Время машины: её часовой пояс, местное время сейчас (часы этого пояса), «Включена с» и сколько минут она работает "
                         "(от «Включена с»; неизвестно — 0).",
    "act:machine.state": "Дефекты подключения к машине для всех. Задать — поставить заполненные поля; Добавить — прибавить к текущим "
                         "(минус — убавить; проценты не выше 100, ниже нуля не бывает); Сбросить — всё в ноль. Пустое поле не меняется. "
                         "Задержка — ответ терминала с паузой, построчно; помехи — процент сбитых символов в выводе; обрывы — шанс за минуту "
                         "работы с машиной; КБ/с — скорость xfer; помехи ввода — подмена набираемых символов; перегрузка — доля команд, "
                         "которые не выполняются; помехи изображения — картинка стола как у плохой трансляции.",
    "ent:os": "Операционная система: выбрать в ноде или проводом «ОС» из машины. Код (AETHER), название, диалект путей (unix, windows, "
              "vms…), приветствие и все машины на ней.",
    "act:machine.change": "Свойство машины для всех — что выбрано: имя, адрес, ОС, часовой пояс, ключ хоста (пусто — новый случайный: игрок, "
                          "который уже заходил, заметит подмену), приветствие ({note}), «Включена с» (от неё считается uptime; включение машины её не трогает). Графика — без неё rcon отказывает, входят только rshell, xfer и раздачи. Число мест — сколько игроков одновременно (пусто — без ограничения). Помехи, задержка и прочие дефекты — «Машина: Изменить состояние».",
    "act:account.change": "Учётка: почта, пароль (для всех), выражение ключей, точки входа и группы (добавить или убрать, одно или список), "
                          "токены: создать (выход «Токен» — строка, её можно вписать в письмо) или удалить (пусто — все).",
    "act:account.access": "Заблокировать вход на учётку на N минут (игроку или всем, с текстом) или снять блокировку.",
    "act:account.manage": "Создать учётку на машине (выход «Учётка») или удалить (учётку игрока — нельзя). «Инициатора» — его место на "
                          "этой машине (одна на машину): домашняя папка, почта, ключи, как на aether-main. Логин можно шаблоном: {player}.",
    "manual": "Кнопка автора в панели ноды. Выход «Автор» — кто нажал. Для проверки можно запустить за игрока: он станет игроком потока. Только старт.",
    "try:machine": "Вход на выбранную машину. Tab — граф входа этой машины: от «Попытки» до «Ответить», без ожиданий. "
                   "Выходы ноды — сокеты «Выхода» внутри графа: события и данные.",
    "attempt:machine": "Игрок пытается войти: подробности попытки. Дальше проверки и действия, конец — «Ответить».",
    "on:machine.status": "Машину остановили или запустили (для всех). Пустая машина — любая.",
    "on:terminal.command": "Игрок ввёл команду в терминале. Команда и аргументы понимают *.",
    "on:placement.changed": "Файл игрока изменился: отредактирован, перенесён, удалён в корзину, возвращён, стёрт насовсем. "
                            "Провод «Размещение» — следить за этим файлом, иначе фильтры (объект — любая его копия, путь *, машина). "
                            "«Было» — где файл был, «Размещение» — где он теперь (после удаления — в корзине). "
                            "Ждущая нода сама идёт за файлом, если он переехал.",
    "on:placement.opened": "Игрок открыл файл. Провод «Размещение» — этот файл; иначе фильтры: объект, путь (*), машина.",
    "on:placement.appeared": "У игрока появился новый файл: сделал сам (вырезка, подпись, текст из архива) или скопировал. "
                             "Объект, впервые попавший к игроку, — «Объект: Получен».",
    "on:object.got": "Объект лёг игроку его руками: из письма или архива, с форума, с сервера, с другой машины, собран из частей, ключ. Выданное сценарием или автором сюда не попадает.",
    "on:character.mail": "Старое: теперь «Персонаж: Получил сообщение».",
    "on:character.wrote": "Игрок написал персонажу: письмо на его адрес, ответ или полный позывной на форуме, позывной в эфире. Кто — выход "
                          "«Игрок»; «Сообщение» — провод в «Персонаж: Ответить» (у письма, выбранного вариантом возможности, его нет).",
    "act:character.say": "Персонаж пишет первым. Почта — кому: Учётке (события), Лично (учётка игрока на aether-main), Всем (в каждую "
                         "учётку игрока при открытии почты) или указать: учётки, адреса, игроки, персонажи (ящик с их адресом). Тема и текст "
                         "или готовое письмо. Форум — новая тема или в тему с этим заголовком. Эфир — частота, позывной персонажа. Уходит "
                         "сразу; позже — нода «Ждать» перед ней.",
    "act:character.reply": "Ответ на сообщение туда же: письмо отправителю, сообщение под постом, передача на той же частоте. У кукловода "
                           "сообщение становится отвеченным: «Отправлено сценарием …».",
    "on:air.sent": "Игрок передал в эфир на частоте. Позывной — его станции. Передачи станций и персонажей — событие «Эфир: Передача станции».",
    "on:air.station": "В эфир передала станция (ответчик автора или персонаж). Персонаж — у станции с персонажем. Игрока нет.",
    "on:moment.status": "Момент мира начался или кончился.",
    "on:tag": "Тег владельца поставили или сняли. Владелец и «чьё» — как у ноды «Тег».",
    "on:count": "Счётчик владельца изменился: выходы — новое значение и разница.",
    "on:count.threshold": "Счётчик перешёл порог: «Дошёл» — снизу вверх, «Ушёл ниже» — сверху вниз.",
    "on:time": "Один раз в игровую дату и время. Ход мировой — без инициатора; по игрокам — «Найти по условию» → «Для каждого».",
    "on:schedule": "По игровому времени: каждый день в ЧЧ:ММ, по дням недели или каждые N минут. Ход мировой — без инициатора.",
    "signal": "Сигнал от «Послать сигнал» с тем же именем: связывает сценарии без проводов.",
    "wait": "Ждать время, до времени (ЧЧ:ММ) или пока условие не станет верным. Время игровое, если не отмечено «реальное».",
    "check": "Проверить условие сейчас (провод да/нет или выражение: ключи, tag:, count:, world: — у инициатора) и пойти в «Истина» или «Ложь». "
             "Несколько — цепочкой: «Ложь» в следующее «Если» (если — иначе если — иначе).",
    "choose": "Старое: теперь цепочка «Направить: Если».",
    "random": "Случайная ветка; чем больше вес, тем чаще.",
    "turns": "Каждый следующий поток — в следующую ветку (раздать разные части по очереди). После последней — снова с первой или в «Закончились». "
             "Счёт общий на весь мир.",
    "first": "Первые N игроков в мире идут в «Успел», остальные — в «Опоздал» (first decoded by).",
    "once": "Первый проход — «Впервые», дальше — «Уже было». За игру — один на всех; на каждого игрока — первый проход инициатора.",
    "all": "Ветки одного потока сходятся: дальше, когда пришли все входы, в любом порядке. Инициатор — кто сдвинул последним.",
    "race": "Ветки одного потока: дальше по первому пришедшему входу (выход — какой пришёл первым); остальные ожидания, ведущие сюда, снимаются. "
            "«Ответ или 30 минут»: триггер ответа и «Ждать 30 мин» в два входа.",
    "some": "Ветки одного потока: дальше, когда пришли любые «Сколько нужно» входов из «Сколько входов»; остальные ожидания, ведущие сюда, снимаются.",
    "end": "Прохождение закончено с исходом; все ждущие ветки снимаются.",
    "answer": "Ответ в графе попытки (у машины, сервера, слоя): впустить, отказать, заблокировать или как обычно — решают поля вещи.",
    "reroute": "Точка излома провода. Ничего не делает.",
    "group": "Группа нод (Ctrl+G). Tab — войти. Сокеты — её «Вход» и «Выход».",
    "group_in": "Вход группы или сценария: сокеты слева у ноды группы; сюда приходит «Запустить сценарий».",
    "group_out": "Выход группы или сценария: сокеты справа у ноды группы.",
    "scenario": "Другой сценарий целиком, как группа. Идёт в ходах этого сценария; его старты здесь не срабатывают.",
    "launch": "Запустить другой сценарий: новый ход с игроком этого хода, не дожидаясь его.",
    "send_signal": "Послать сигнал: будит ноды «Сигнал» с тем же именем — с инициатором или у всех.",
    "stage": "Отметка хода: счётчик «прошли» на холсте.",
    "note": "Заметка на холсте. Не исполняется.",
    "frame": "Рамка вокруг нод. Не исполняется.",
    "text": "Текст для входов. {имя} в тексте заменяется значением подстановки с этим именем (любой тип: вещь — ключом, список — через "
            "запятую). Написали «{» — появилась подстановка; заполнили — появляется следующая.",
    "number": "Число: значение для входов.", "boolean": "Да/нет: значение для входов.",
    "compare": "Сравнить A и B: числа — как числа, даты — как даты (раньше — меньше), остальное — как текст без учёта регистра. «По образцу» понимает *.",
    "time.get": "Сейчас или заданное «Другое» (текст или провод даты). Дата — эта дата в 00:00, Время — это время сегодня. "
                "Выходы: дата и время, дата текстом, время текстом. Время мировое.",
    "time.calc": "Разница — A − B в секундах, минутах, часах или днях (целое; A пусто — сейчас): давно ли — «Последняя активность» в B. "
                 "Сдвиг — A плюс дни, часы, минуты и секунды (минус — назад).",
    "time.zone": "Те же часы в другом поясе: на выходе — дата и время, как их показывают часы этого пояса (пояс в значении не хранится).",
    "time.parts": "Год, месяц, день, час, минута, день недели (1 — пн), дата и время текстом. С машиной — в её часовом поясе.",
    "logic": "И — все входы да; Или — хоть один да; Не — наоборот; Исключающее или — ровно один да. Подключили вход — появляется следующий.",
    "fact": "Условие на факты инициатора: ключи, tag:, count:, world:. Верно или нет.",
    "math": "Посчитать A и B. «Случайное» — целое от A до B; округление, модуль и смена знака берут только A.",
    "read": "Прочитать сейчас: счётчик или метку мира, счётчик или метку инициатора.",
    "ent:machine": "Машина: выбрать в ноде, получить проводом или найти по хосту/имени из текста. Свойства — как сейчас. Диски — что "
                   "подключено в её точках (список «Машина: Диск»). Сессии — все игроки на машине, свежие первыми: в «Сессия: Закрыть» — "
                   "выбросить всех с машины. Дефекты связи — атрибут «Машина: Состояние», часы — «Машина: Время».",
    "ent:volume": "Диск автора (том): по слагу или названию. «Где подключён» — точки машин, где он стоит.",
    "ent:mount": "Что стоит в точке машины: провод «хост:/точка» или Машина + Точка. Тип: диск (том автора, выход «Диск») или сетевой "
                 "(Хост, Путь, Учётка хоста). «Есть» — подключено ли сейчас.",
    "act:machine.disk": "Подключить диск в точку машины (в занятую — ляжет сверху), подключить по сети путь другой машины (хост должен его "
                        "отдавать; учётка хоста, пусто — guest) или отключить: провод «Машина: Диск», либо Машина + Точка (всё в ней) "
                        "или Машина + Диск (этот диск с машины). Для всех. Выход — «Машина: Диск».",
    "ent:server": "Сетевой ресурс (nreq, nget): по адресу.", "ent:object": "Объект библиотеки — содержимое, общее для всех; по слагу или названию.",
    "ent:character": "Персонаж: по коду или имени.", "ent:section": "Раздел форума: по номеру или названию.",
    "ent:moment": "Момент мира: по имени или названию; «Идёт» — сейчас ли он.",
    "ent:player": "Игрок: пусто — инициатор, иначе по логину.",
    "ent:session": "Сессия — игрок на учётке. Активна — его рабочий стол или терминал там сейчас. Статус: активна · подключена "
                   "(открыта в цепочке мостов, игрок работает дальше) · закрыта. Тип — как вошли: local · rcon · rshell. Где: стол · "
                   "терминал · стол и терминал · пусто.",
    "thing.find": "Вещи выбранного вида, для которых условие верно. Условие — как у условий доступа (and, or, not, скобки); атом про саму "
                  "вещь — вид без вещи: tag:account:имя, count:machine:имя >= 3, tag:account:имя@player (значение для инициатора), "
                  "у учётки — group:account:группа (в группе прав). "
                  "tag:world:…, tag:имя (инициатора) и теги конкретных вещей одинаковы для всех и только дополняют: без атома про вещь "
                  "условие не отбирает. «Среди» — искать только в этом списке. Порядок: по имени, по счётчику, по времени тега (когда поставили), по "
                  "времени изменения тега или счётчика (у кого его нет — в конце) или случайно; «Сколько взять» — первые N.",
    "session.find": "Текущая — где произошло действие (в условии у «Изменить» — где игрок применяет возможность). Все — сессии игрока "
                    "(пусто — инициатор), Машина — сессии всех игроков на машине, Учётка — всех игроков на учётке: списком, свежие первыми. "
                    "«Только активные» — кто там сейчас.",
    "act:screen": "Показать на экране: уведомление, бегущую строку, окна ошибок, окно с адресом, чёрный экран или сцену. Кому: инициатору, "
                  "всем игрокам в игре или указанным — игрок, сессия (её игрок), учётка или машина (кто сейчас на них); одно или список. "
                  "У учётки, сессии и машины эффект ждёт, пока стол игрока (у терминальных — терминал) окажется там; через 15 минут устаревает.",
    "act:session.close": "Закрыть сессию: игрока выбрасывает с учётки при следующем запросе (рабочий стол или терминал возвращаются "
                         "на предыдущую в цепочке). Одна сессия или список; пусто — текущая (где произошло действие).",
    "list.make": "Собрать список из входов (что угодно): подключили последний — появился следующий; пустые не попадают. Все провода "
                 "одного типа — список этого типа, иначе — текста. «Количество» — сколько вышло.",
    "list.content": "Количество элементов; Элемент — первый, последний или по номеру («Есть» — нашёлся ли); Содержит — есть ли значение "
                    "(одно или хоть одно из списка; текст — без учёта регистра). Тип элемента — по поданному списку.",
    "list.action": "Новый список: Добавить значение (в конец, в начало или на номер), Убрать (последний, первый или по номеру), "
                   "Достать по номеру или по элементу — тогда ещё «Элемент» и «Есть». Номера с 1.",
    **HELP_EACH,
    "foreach": "Для каждого элемента списка — ветка «Каждый» с данными «Элемент» и «Номер», потом «Готово». В ветке «Каждый» нельзя ждать.",
    "switch": "Если «Если» — да, значение «Да», иначе «Нет». Так выход получает значение по условию.",
    "allowed": "поля вещи пустили (у «как обычно»)", "refused": "поля вещи отказали (у «как обычно»)",
    "ent:tag": "Тег владельца: мира, игрока, персонажа, машины, сервера или объекта; у вещи — общий или свой у игрока.",
    "ent:count": "Счётчик владельца, как у «Тега»; «Подпись» — подпись значения из описания счётчика («2» — «Архив»).",
    "act:tag": "Поставить или снять тег владельца (мир, игрок, вещь; у вещи — общий или для игрока).",
    "act:count": "Прибавить к счётчику владельца или задать его.",
    "act:machine.status": "Остановить, запустить или перезагрузить машину — для всех. Остановленная не находится, сессии обрываются. "
                          "Во «Когда» можно условие: пока верно — остановлена или на обслуживании, стало ложно — запущена.",
    "act:terminal": "Строка или сцена во все открытые терминалы игрока.",
    "act:mail": "Готовое письмо игроку: в ящик учётки события (ответ туда, откуда писали; его видят все на учётке) или лично — в его "
                "ящик на aether-main; можно с задержкой. Или всем при открытии почты.",
    "act:forum": "Запись на форуме от системы или персонажа: новая тема или ответ в тему с таким заголовком.",
    "act:moment": "Начать или закончить момент мира сейчас. Во «Когда» можно условие: верно — сделать, стало ложно — наоборот.",
    "while": "Условие стало верным или ложным: «Стало верно» и «Стало ложно» запускают ход. Для каждого игрока (его факты, пересчёт на его событиях) "
             "или для мира (пересчёт на любом событии и по времени). Первая проверка с ложным условием ничего не запускает.",
    "ent:layer": "Слой файла игрока (провод с «Размещение → Слои» или события слоя): тип, индекс (1 — верхний), снят ли, сколько попыток осталось (-1 — без ограничения), добавлен ли поверх описания, чьё размещение.",
    "on:layer.added": "Сценарий или автор положил слой поверх файла. Провод «Слой» — этот слой, «Размещение» — любой слой файла; иначе фильтры: объект, тип.",
    "on:layer.changed": "Игрок что-то сделал со слоем файла: снял, ошибся, истратил попытки (добавленный слой — событие «Слой: Добавлен»). Провод «Слой» — этот слой, «Размещение» — любой слой файла; иначе фильтры: объект, тип. Тип, размещение, объект — у ноды «Слой».",
    "act:layer": "Сделать со слоем: снять (как игрок — хуки срабатывают; не верхний — вместе со всем, что над ним), снять тихо (без хуков), "
                 "сбросить попытки. Размещение — его верхний слой.",
    "try:net.request": "Запрос к выбранному серверу (nreq). Tab — граф попытки сервера; выходы — сокеты «Выхода» внутри.",
    "try:net.download": "Скачивание с выбранного сервера (nget). Tab — граф попытки сервера; выходы — сокеты «Выхода» внутри.",
    "attempt:server": "Игрок обращается к серверу: подробности попытки. Дальше проверки и действия, конец — «Ответить».",
    "ent:placement": "Размещение — файл в виде игрока: машина и путь (пусто «Игрок» — инициатор) или провод «Размещение». "
                     "Свойства — как сейчас: есть ли файл, какой в нём объект, в корзине ли.",
    "find": "Размещения игрока на его машинах: с объектом (пусто — любые файлы), путь по образцу *, вне корзины, в корзине или везде. "
            "Список — «Для каждого» или «Список: …». Перенос и переименование файла его не теряют.",
    "do:flag": "Поставить тег игроку (tag:имя).", "do:unflag": "Снять тег игрока.",
    "do:letter": "Прислать готовое письмо в ящик учётки игрока (можно с задержкой).",
    "do:kick": "Старое: теперь «Сессия: Закрыть».",
    "do:world_flag": "Поставить метку мира.", "do:world_unflag": "Снять метку мира.",
    "do:world_count": "Прибавить к счётчику мира.",
    "do:news": "Опубликовать новость; важная всплывает на столе.",
    "do:air": "Передать в эфир от станции на частоте; можно с шифром.",
    "do:letter_all": "Письмо всем: придёт каждому при открытии почты (можно ограничить машинами и ОС).",
    "do:forum": "Запись на форуме: новая тема или дописать в тему, от системы или персонажа.",
    "do:notify": "Уведомление на столе игрока.", "do:ticker": "Бегущая строка вверху стола игрока.",
    "do:windows": "Засыпать стол игрока окнами ошибок.", "do:open_window": "Открыть окно с адресом на столе игрока.",
    "do:blackout": "Чёрный экран с текстом; после него стол перезагружается.",
    "do:terminal_text": "Строка во все открытые терминалы игрока (нет терминала — уведомление).",
    "do:terminal_scene": "Сыграть сцену в открытых терминалах игрока.", "do:scene": "Сыграть сцену на весь экран стола игрока.",
    "do:player_count": "Прибавить к счётчику игрока или задать его (count:имя в условиях).",
    "do:machine_power": "Остановить, запустить или перезагрузить машину — для всех. Остановленная не находится, сессии обрываются.",
    "do:net_node": "Узел сервера: новый токен или ответ страницы — для всех.",
    "do:moment_start": "Начать момент мира сейчас.", "do:moment_end": "Закончить момент мира сейчас.",
    "do:character_tag": "Поставить или снять тег персонажа (tag:character:КОД:тег в условиях).",
}

SOCKET_HELP = {
    "sender": "как игрок подписался: обратный адрес письма, ник на форуме или позывной в эфире", "from_address": "обратный адрес письма игрока",
    "nick": "ник, под которым игрок написал на форуме", "subject": "тема письма или название темы форума",
    "attempt": "игрок пытается войти или запросить: ждёт «Ответить»",
    "login": "игрок вошёл на машину", "stopped": "машину остановили", "started": "машину запустили",
    "request": "игрок запросил страницу (nreq)", "download": "игрок скачал файл (nget)", "denied": "сервер отказал (токен или сценарий)",
    "run": "игрок выполнил команду", "read": "игрок открыл файл", "deleted": "игрок удалил файл", "restored": "игрок вернул файл из корзины",
    "got": "файл или ключ попал к игроку / пришёл сигнал", "joined": "игрок собрал ключ из частей",
    "layer_removed": "игрок снял слой", "layer_attempt": "неверная попытка снять слой", "layer_failed": "попытки снять слой кончились",
    "mail": "игрок написал персонажу письмо", "air": "игрок позвал персонажа в эфире", "forum": "игрок написал персонажу на форуме",
    "sent": "передача на частоте", "topic": "новая тема в разделе", "reply": "ответ в разделе",
    "set": "метку поставили", "unset": "метку сняли", "on": "метку мира поставили", "off": "метку мира сняли",
    "changed": "значение изменилось", "reached": "значение дошло до порога", "fire": "запуск",
    "timeout": "событие не случилось за таймаут", "next": "дальше", "fail": "действие не выполнилось; причина в журнале мира",
    "yes": "условие верно", "no": "условие неверно", "else": "ни одна строка не верна", "pass": "пропущен", "late": "не успел",
    "again": "уже было", "in": "когда сюда приходит событие, нода выполняется", "ref": "вещь этой ноды (из события, а без него — та, что выбрана в ноде)",
    "value": "значение", "player": "инициатор (имя)", "path": "путь файла из события", "layer": "слой из события",
    "address": "адрес сервера", "command": "команда", "args": "аргументы команды", "text": "текст из события", "channel": "канал: mail, air, forum",
    "callsign": "позывной", "title": "заголовок или название", "lit": "стоит ли метка",
    "name": "имя или название", "host": "хост машины", "system": "код ОС машины", "up": "машина работает (не остановлена)",
    "code": "код персонажа", "active": "персонаж активен", "archived": "раздел в архиве", "running": "момент идёт сейчас",
    "format": "формат объекта", "has": "у игрока есть копия вне корзины", "where": "машина:путь первой копии", "count": "сколько копий вне корзины",
    "trash": "какая-то копия в корзине", "edited": "игрок поменял текст копии", "caption": "подпись значения",
    "stopped": "машину остановили", "viewed": "игрок открыл файл", "via": "откуда пришёл объект", "from_placement": "где файл был до изменения / с чего скопирован",
    "edited": "игрок сохранил правку текста",
    "opened": "игрок открыл файл", "changed": "игрок сохранил правку", "purged": "игрок стёр файл насовсем", "moved": "игрок перенёс файл",
    "appeared": "у игрока появился новый файл", "delta": "на сколько изменилось",
    "up": "значение дошло до порога снизу", "down": "значение ушло ниже порога", "ended": "момент кончился", "machine": "машина события",
    "item": "объект события", "moment": "момент события", "freq": "частота", "placement": "файл игрока: машина и путь", "exists": "файл есть у игрока",
    "entered": "игрок вошёл (кто бы ни решал: граф или поля машины)", "denied": "в доступе отказано", "reason": "почему отказ: пароль, ключ, окно, граф…",
    "go": "попытка: дальше проверки, конец — «Ответить»", "each": "по разу на элемент списка", "done": "все элементы пройдены",
    "index": "номер элемента (с 1)", "found": "элемент с таким номером есть", "list": "список", "given": "что игрок ввёл, снимая слой", "kind": "тип слоя",
    "number": "номер слоя сверху (у слоя, добавленного игроком, — 0)", "removed": "игрок уже снял этот слой", "left": "сколько слоёв осталось у игрока",
    "server": "сетевой ресурс",
}


# ---------- данные ----------

def _data(name, label, summary, fields, out_type, out_label="Значение", **extra):
    register(Kind(name, label, DATA, summary, fields, ins=(), **extra))
    DATA_OUTS[name] = (Sock("value", out_label, out_type),)


_P = ("@player",)
DATA_OUTS["foreach"] = (Sock("item", "Элемент", ELEMENT), Sock("index", "Номер", "number"))
for _kind, _outs in {
    "signal": (),
    "manual": (),
}.items():
    DATA_OUTS[_kind] = _outs + (Sock("player", "Игрок", "player", "@player"),)

_data("text", "Текст", "{value}", (Field("value", "Текст", "text", "{игрок} открыл {файл}"), Field("subs", "Подстановки", "hidden")), "text", "Текст",
      grow=Grow("subs", "s", "text", named=True, needs="value"))
_data("number", "Число", "{value}", (Field("value", "Число", "number"),), "number", "Число")
_data("boolean", "Да/нет", "{value}", (Field("value", "Да", "bool"),), "bool", "Да/нет")
_data("compare", "Сравнить", "{op}",
      (Field("a", "A", "text"), Field("op", "Как", "select", "", False, (("eq", "="), ("ne", "≠"), ("gt", ">"), ("ge", "≥"), ("lt", "<"), ("le", "≤"),
                                                                       ("contains", "содержит"), ("like", "по образцу *"))), Field("b", "B", "text")),
      "bool", "Верно")
LOGIC = (("and", "И"), ("or", "Или"), ("not", "Не"), ("xor", "Исключающее или"))
_data("logic", "Логика", "", (Field("op", "Действие", "select", "", False, LOGIC), Field("values", "Входы", "hidden")), "bool", "Да/нет",
      title="op", grow=Grow("values", "v", "bool", min=2, single=("not",)))
_THING_KINDS = (("account", "Учётка"), ("player", "Игрок"), ("character", "Персонаж"), ("machine", "Машина"), ("server", "Сетевой ресурс"),
                ("item", "Объект"))
register(Kind("thing.find", "Найти по условию", ENTITY, "{what}: {expr}", (
    Field("what", "Что ищем", "select", "", False, _THING_KINDS),
    Field("expr", "Условие", "expr", "tag:account:compromised and count:account:fails >= 3", True),
    Field("among", "Среди", OF_LIST),
    Field("order", "Порядок", "select", "", False, (("name", "По имени"), ("count", "По счётчику"), ("tag_time", "По времени тега"),
                                                    ("changed", "По времени изменения"), ("random", "Случайно"))),
    Field("by", "Тег или счётчик", "text", "имя или имя@player", True),
    Field("name_dir", "Сначала", "select", "", False, (("asc", "А→Я"), ("desc", "Я→А"))),
    Field("count_dir", "Сначала", "select", "", False, (("desc", "больше"), ("asc", "меньше"))),
    Field("time_dir", "Сначала", "select", "", False, (("asc", "раньше"), ("desc", "позже"))),
    Field("limit", "Сколько взять", "number", "все"),
), ins=(), typed="what", when={"by": ("order", ("count", "tag_time", "changed")), "name_dir": ("order", ("name",)),
                               "count_dir": ("order", ("count",)), "time_dir": ("order", ("tag_time", "changed"))}))
DATA_OUTS["thing.find"] = (Sock("value", "Найдено", OF_LIST), Sock("first", "Первое", ELEMENT), Sock("count", "Количество", "number"))
_data("fact", "Факт", "{expr}", (Field("expr", "Условие", "expr", "tag:met and world:act>=2", True),), "bool", "Верно")
MATH = (("add", "Сложить"), ("sub", "Вычесть"), ("mul", "Умножить"), ("div", "Разделить"), ("mod", "Остаток"), ("pow", "Степень"),
        ("min", "Минимум"), ("max", "Максимум"), ("random", "Случайное"),
        ("round", "Округлить"), ("floor", "Округлить вниз"), ("ceil", "Округлить вверх"), ("abs", "Модуль"), ("neg", "Сменить знак"))
UNARY = ("round", "floor", "ceil", "abs", "neg")
_data("math", "Математика", "",
      (Field("op", "Действие", "select", "", False, MATH), Field("a", "A", "number"), Field("b", "B", "number")), "number", "Число",
      title="op", when={"b": ("op", tuple(v for v, _ in MATH if v not in UNARY))})
_data("read", "Прочитать", "{what} {name}",
      (Field("what", "Что", "select", "", False, (("world_counter", "счётчик мира"), ("player_counter", "счётчик игрока"), ("world_flag", "метка мира"),
                                                  ("player_flag", "метка игрока"))), Field("name", "Имя", "text", "", True)), "number", "Значение")
DATA_OUTS["read"] = (Sock("value", "Значение", "number"), Sock("lit", "Стоит", "bool"))
_OF = Field("of", "Тип элементов", "hidden", "", False, tuple(ELEMENTS.items()))     # пишет Студия по типу проводов (types_from)
_data("list.make", "Список", "", (_OF, Field("items", "Элементы", "hidden")), OF_LIST, "Список",
      typed="of", grow=Grow("items", "e", "text", min=2), types_from=("@rows",))
DATA_OUTS["list.make"] += (Sock("count", "Количество", "number"),)
register(Kind("list.content", "Список: Содержимое", DATA, "", (
    _OF, Field("mode", "Что", "switch", "", False, (("count", "Количество"), ("item", "Элемент"), ("has", "Содержит"))),
    Field("list", "Список", OF_LIST),
    Field("pick", "Какой", "switch", "", False, (("first", "Первый"), ("last", "Последний"), ("number", "По номеру"))),
    Field("number", "Номер", "number", "1"), Field("value", "Значение", MANY + ELEMENT),
), ins=(), typed="of", title="mode", types_from=("list",),
   when={"pick": ("mode", ("item",)), "number": [("mode", ("item",)), ("pick", ("number",))], "value": ("mode", ("has",))},
   outs_when={"count": ("mode", ("count",)), "item": ("mode", ("item",)), "found": ("mode", ("item",)), "has": ("mode", ("has",))}))
DATA_OUTS["list.content"] = (Sock("count", "Количество", "number"), Sock("item", "Элемент", ELEMENT), Sock("found", "Есть", "bool"),
                             Sock("has", "Содержит", "bool"))
register(Kind("list.action", "Список: Действие", DATA, "", (
    _OF, Field("mode", "Что", "switch", "", False, (("add", "Добавить"), ("remove", "Убрать"), ("take", "Достать"))),
    Field("list", "Список", OF_LIST), Field("value", "Значение", ELEMENT),
    Field("where", "Где", "switch", "", False, (("end", "В конец"), ("start", "В начало"), ("index", "По номеру"))),
    Field("at", "Номер", "number", "1"),
    Field("by", "Как", "switch", "", False, (("index", "По номеру"), ("value", "По элементу"))),
    Field("number", "Номер", "number", "1"), Field("item", "Элемент", ELEMENT),
), ins=(), typed="of", title="mode", types_from=("list",),
   when={"value": ("mode", ("add",)), "where": ("mode", ("add", "remove")), "at": [("mode", ("add", "remove")), ("where", ("index",))],
         "by": ("mode", ("take",)), "number": [("mode", ("take",)), ("by", ("index",))], "item": [("mode", ("take",)), ("by", ("value",))]},
   outs_when={"item": ("mode", ("take",)), "found": ("mode", ("take",))}))
DATA_OUTS["list.action"] = (Sock("list", "Список", OF_LIST), Sock("item", "Элемент", ELEMENT), Sock("found", "Есть", "bool"))
_data("switch", "Выбрать значение", "",
      (Field("condition", "Если", "bool"), Field("yes", "Да", "text"), Field("no", "Нет", "text")), "text", "Значение")
_data("time.get", "Время", "", (
    Field("source", "Когда", "switch", "", False, (("now", "Сейчас"), ("other", "Другое"))),
    Field("what", "", "switch", "", False, (("datetime", "Дата и время"), ("date", "Дата"), ("clock", "Время"))),     # без подписи
    Field("value", "Значение", "datetime", "2031-05-14 21:00 · 2031-05-14 · 21:00", True),
), "datetime", "Дата и время", when={"value": ("source", ("other",))})
DATA_OUTS["time.get"] = (Sock("value", "Дата и время", "datetime"), Sock("date", "Дата", "text"), Sock("clock", "Время", "text"))
register(Kind("time.calc", "Время: Расчёт", DATA, "", (
    Field("mode", "Режим", "switch", "", False, (("diff", "Разница"), ("shift", "Сдвиг"))),
    Field("a", "A", "datetime", "сейчас"), Field("b", "B", "datetime", "", True),
    Field("days", "Дни", "number", "0"), Field("hours", "Часы", "number", "0"), Field("minutes", "Минуты", "number", "0"),
    Field("seconds", "Секунды", "number", "0"),
    Field("unit", "Единица", "switch", "", False, (("seconds", "Секунды"), ("minutes", "Минуты"), ("hours", "Часы"), ("days", "Дни"))),
), ins=(), title="mode", when={"b": ("mode", ("diff",)), "unit": ("mode", ("diff",)),
                               **{name: ("mode", ("shift",)) for name in ("days", "hours", "minutes", "seconds")}},
   outs_when={"diff": ("mode", ("diff",)), "shifted": ("mode", ("shift",))}))
DATA_OUTS["time.calc"] = (Sock("diff", "Разница", "number"), Sock("shifted", "Дата", "datetime"))
_data("time.zone", "Время: Временная зона", "{zone}",
      (Field("value", "Дата", "datetime", "сейчас"), Field("zone", "Пояс", "time_zone", "", True)), "datetime", "Дата")
_data("time.parts", "Время: Части", "", (Field("value", "Дата", "datetime", "сейчас", True), Field("machine", "Машина", "machine", "мировое время")),
      "number", "Год")
DATA_OUTS["time.parts"] = (Sock("year", "Год", "number"), Sock("month", "Месяц", "number"), Sock("day", "День", "number"),
                           Sock("hour", "Час", "number"), Sock("minute", "Минута", "number"), Sock("weekday", "День недели", "number"),
                           Sock("date", "Дата", "text"), Sock("clock", "Время", "text"))
KINDS["read"] = replace(KINDS["read"], hidden=True)                 # теперь «Тег» и «Счётчик»


# ---------- сущности: вещь мира и её свойства сейчас (graph/entities.py) ----------

def _entity(name, label, field, outs):
    register(Kind(name, label, ENTITY, "{%s}" % field.name, (field,), ins=()))
    DATA_OUTS[name] = outs


_entity("ent:machine", "Машина", Field("machine", "Машина", "machine"),
        (Sock("value", "Машина", "machine"), Sock("name", "Имя", "text"), Sock("address", "Адрес", "text"),
         Sock("system", "Операционная система", "os"), Sock("up", "Работает", "bool"), Sock("disks", "Диски", "list:mount"),
         Sock("sessions", "Сессии", "list:session"), Sock("display", "Графика", "bool"), Sock("seats", "Мест", "number"),
         Sock("taken", "Занято мест", "number")))
_entity("ent:os", "Операционная система", Field("system", "Операционная система", "system"),
        (Sock("value", "ОС", "os"), Sock("code", "Код", "text"), Sock("name", "Название", "text"), Sock("dialect", "Диалект", "text"),
         Sock("greeting", "Приветствие", "text"), Sock("machines", "Машины", "list:machine")))


def _attr(name, label, field, outs):
    """Атрибут: одна сторона сущности. Вещь — проводом из сущности (или выбрана в ноде), выходы — её свойства этой темы."""
    register(Kind(name, label, ATTR, "{%s}" % field.name, (field,), ins=()))
    DATA_OUTS[name] = outs


_attr("attr:machine.state", "Машина: Состояние", Field("machine", "Машина", "machine"),
      tuple(Sock(name, label, "number") for name, label, _, _ in STATE) + (Sock("defects", "Есть дефекты", "bool"),))
_attr("attr:machine.time", "Машина: Время", Field("machine", "Машина", "machine"),
      (Sock("zone", "Часовой пояс", "text"), Sock("local", "Местное время", "datetime"), Sock("booted", "Включена с", "datetime"),
       Sock("uptime", "Работает, мин", "number")))
_attr("attr:account.access", "Учётка: Доступ", Field("account", "Учётка", "account", "логин@хост"),
      (Sock("groups", "Группы", "list:text"), Sock("endpoints", "Точки входа", "list:text"), Sock("root", "Root", "bool"),
       Sock("blocked", "Заблокирована", "bool"), Sock("keys", "Выражение ключей", "text"), Sock("tokens", "Токены", "list:text")))
_entity("ent:volume", "Диск", Field("volume", "Диск", "volume"),
        (Sock("value", "Диск", "volume"), Sock("name", "Название", "text"), Sock("where", "Где подключён", "list:mount")))
register(Kind("ent:mount", "Машина: Диск", ENTITY, "{point}{mount}", (
    Field("mount", "Диск машины", "mount", "хост:/точка"), Field("machine", "Машина", "machine"), Field("point", "Точка", "path", "/mnt/archive"),
), ins=(), covers={"mount": ("machine", "point")}))
DATA_OUTS["ent:mount"] = (Sock("value", "Диск машины", "mount"), Sock("machine", "Машина", "machine"), Sock("point", "Точка", "text"),
                          Sock("type", "Тип", "text"), Sock("volume", "Диск", "volume"), Sock("host", "Хост", "machine"),
                          Sock("path", "Путь", "text"), Sock("account", "Учётка", "account"), Sock("read_only", "Только чтение", "bool"),
                          Sock("exists", "Есть", "bool"))
_entity("ent:server", "Сетевой ресурс", Field("server", "Сетевой ресурс", "server"),
        (Sock("value", "Сетевой ресурс", "server"), Sock("title", "Название", "text")))
_entity("ent:object", "Объект", Field("item", "Объект", "object"),
        (Sock("value", "Объект", "item"), Sock("name", "Название", "text"), Sock("format", "Формат", "text")))
_entity("ent:character", "Персонаж", Field("character", "Персонаж", "character"),
        (Sock("value", "Персонаж", "character"), Sock("name", "Имя", "text"), Sock("callsign", "Позывной", "text"),
         Sock("active", "Активен", "bool")))
_entity("ent:section", "Раздел", Field("section", "Раздел", "section"),
        (Sock("value", "Раздел", "section"), Sock("title", "Название", "text"), Sock("archived", "В архиве", "bool")))
_entity("ent:moment", "Момент", Field("moment", "Момент", "moment"),
        (Sock("value", "Момент", "moment"), Sock("title", "Название", "text"), Sock("running", "Идёт", "bool")))
_entity("ent:player", "Игрок", Field("player", "Игрок", "player", "инициатор"),
        (Sock("value", "Игрок", "player"), Sock("callsign", "Позывной", "text"), Sock("accounts", "Учётки", "list:account"),
         Sock("sessions", "Сессии", "list:session")))
_entity("ent:session", "Сессия", Field("session", "Сессия", "session", "игрок/логин@хост"),
        (Sock("value", "Сессия", "session"), Sock("player", "Игрок", "player"), Sock("machine", "Машина", "machine"),
         Sock("account", "Учётка", "account"), Sock("seen", "Последняя активность", "datetime"), Sock("active", "Активна", "bool"),
         Sock("status", "Статус", "text"), Sock("via", "Тип", "text"), Sock("where", "Где", "text")))
register(Kind("session.find", "Сессия: Найти", ENTITY, "", (
    Field("mode", "Какие", "switch", "", False, (("current", "Текущая"), ("all", "Все"), ("machine", "Машина"), ("account", "Учётка"))),
    Field("player", "Игрок", "player", "инициатор"), Field("machine", "Машина", "machine", "", True),
    Field("account", "Учётка", "account", "логин@хост", True),
    Field("active", "Только активные", "bool"),
), ins=(), title="mode", plural={"value": ("mode", ("all", "machine", "account"))},
   when={"player": ("mode", ("all",)), "machine": ("mode", ("machine",)), "account": ("mode", ("account",)),
         "active": ("mode", ("all", "machine", "account"))}))
_SAY = ("mail", "forum", "air")
register(Kind("act:character.say", "Персонаж: Написать", ACTION, "{character}", (
    Field("channel", "Канал", "switch", "", False, (("mail", "Почта"), ("forum", "Форум"), ("air", "Эфир"))),
    Field("character", "От кого", "character", "", True),
    Field("to", "Кому", "switch", "", False, (("event", "Учётке"), ("home", "Лично"), ("all", "Всем"), ("list", "Указать"))),
    Field("targets", "Адресаты", "many:account|player|character|text", "учётка, адрес, игрок или персонаж", True),
    Field("letter", "Готовое письмо", "letter", "нет — тема и текст"), Field("subject", "Тема", "text", "", True),
    Field("section", "Раздел", "section", "", True),
    Field("topic", "Куда", "switch", "", False, (("new", "Новая тема"), ("append", "В тему"))), Field("title", "Заголовок темы", "text", "", True),
    Field("freq", "Частота, МГц", "text", "7.205; пусто — вызывная"),
    Field("text", "Текст", "textarea", "{player}, {login}, {host} и подробности события", True),
), (Sock("next", "Сделано"), Sock("fail", "Не вышло")), title="channel",
   when={"to": ("channel", ("mail",)), "targets": [("channel", ("mail",)), ("to", ("list",))], "letter": ("channel", ("mail",)),
         "subject": ("channel", ("mail",)), "section": ("channel", ("forum",)), "topic": ("channel", ("forum",)),
         "title": ("channel", ("forum",)), "freq": ("channel", ("air",))}))
register(Kind("act:character.reply", "Персонаж: Ответить", ACTION, "", (
    Field("message", "Сообщение", "message", "провод от «Получил сообщение»", True),
    Field("text", "Текст", "textarea", "{player} и подробности события", True), Field("subject", "Тема", "text", "Re: тема письма"),
), (Sock("next", "Сделано"), Sock("fail", "Не вышло"))))
register(Kind("act:session.close", "Сессия: Закрыть", ACTION, "{session}", (
    Field("session", "Сессия", "many:session", "текущая"),
), (Sock("next", "Сделано"), Sock("fail", "Не вышло"))))
DATA_OUTS["session.find"] = (Sock("value", "Сессия", "session"),)
def _layer_types():
    from filesystem.layers.registry import registry

    return tuple((name, name) for name in registry.names())


# слой — в файле конкретного игрока: «игрок@машина:/путь#c2» (c — слой описания по номеру, a — добавленный поверх)
register(Kind("ent:layer", "Слой", ENTITY, "{layer}", (Field("layer", "Слой", "layer", "игрок@машина:/путь#c1", True),), ins=()))
DATA_OUTS["ent:layer"] = (Sock("type", "Тип", "text"), Sock("index", "Индекс", "number"), Sock("removed", "Снят", "bool"),
                          Sock("attempts", "Осталось попыток", "number"), Sock("added", "Добавленный", "bool"),
                          Sock("placement", "Размещение", "placement"))
def _value_kind(name, label, outs):
    from engine.actions import OWNER_FIELDS

    register(Kind(name, label, ENTITY, "{owner} {name}", (*OWNER_FIELDS, Field("name", "Имя", "text", "", True)), ins=(),
                  subgroup="Теги и счётчики", when=OWNER_WHEN))
    DATA_OUTS[name] = outs


_value_kind("ent:tag", "Тег", (Sock("on", "Стоит", "bool"),))
_value_kind("ent:count", "Счётчик", (Sock("value", "Значение", "number"), Sock("caption", "Подпись", "text")))
register(Kind("ent:placement", "Размещение", ENTITY, "{machine}:{path}", (
    Field("placement", "Размещение", "placement", "игрок@машина:/путь"), Field("machine", "Машина", "machine"), Field("path", "Путь", "path"),
    Field("player", "Игрок", "player", "инициатор"),
), ins=(), covers={"placement": ("machine", "path", "player")}))
DATA_OUTS["ent:placement"] = (Sock("value", "Размещение", "placement"), Sock("item", "Объект", "item"), Sock("machine", "Машина", "machine"),
                              Sock("path", "Путь", "text"), Sock("name", "Имя", "text"), Sock("exists", "Есть", "bool"),
                              Sock("trash", "В корзине", "bool"), Sock("edited", "Изменён игроком", "bool"), Sock("layers", "Слои", "list:layer"))
register(Kind("find", "Размещение: Найти", ENTITY, "{item} {path}", (
    Field("item", "Объект", "many:object", "любой"), Field("player", "Игрок", "player", "инициатор"), Field("machine", "Машина", "machine", "любая"),
    Field("path", "Путь", "text", "любой; можно *"),
    Field("where", "Где", "select", "", False, (("live", "Вне корзины"), ("trash", "В корзине"), ("all", "Везде"))),
), ins=()))
DATA_OUTS["find"] = (Sock("value", "Размещения", "list:placement"),)


def out_type(kind, name):
    """Тип выхода: событие или тип данных."""
    for sock in DATA_OUTS.get(kind.name, ()):
        if sock.name == name:
            return sock.type
    return EVENT


def data_out(kind, name):
    return next((sock for sock in DATA_OUTS.get(kind.name, ()) if sock.name == name), None)


# ---------- сокеты ноды ----------

def _count(data, name):
    value = (data or {}).get(name)
    if isinstance(value, list):
        return value
    try:
        return [None] * max(0, min(int(value if value not in (None, "") else 2), 12))
    except (TypeError, ValueError):
        return [None] * 2


def named(data, field_name="sockets"):
    """Сокеты «Входа» или «Выхода» группы: [(имя, подпись)]."""
    out = []
    for item in (data or {}).get(field_name) or []:
        if isinstance(item, dict) and str(item.get("name") or "").strip():
            out.append((str(item["name"]).strip(), str(item.get("label") or item["name"])))
    return out


def rows(kind, data):
    """Строки растущего списка ноды: [{"id", "name", "value"}] (только заполненные; пустая строка на холсте не хранится)."""
    if kind.grow is None:
        return []
    return [item for item in (data or {}).get(kind.grow.field) or [] if isinstance(item, dict) and str(item.get("id") or "")]


def is_row(kind, name):
    """name — вход строки растущего списка (s1, v2…)."""
    grow = kind.grow
    return grow is not None and name.startswith(grow.prefix) and name[len(grow.prefix):].isdigit()


def input_label(kind, data, name):
    """Подпись входа-поля (без «f:»)."""
    found = next((f for f in kind.fields if f.name == name), None)
    if found:
        return found.label
    row = next((item for item in rows(kind, data) if item.get("id") == name), None)
    return str((row or {}).get("name") or name)


def socket_types(data):
    """{имя: тип} сокетов «Входа» или «Выхода» группы (тип по умолчанию — событие)."""
    return {str(item.get("name")).strip(): (item.get("type") or EVENT) for item in (data or {}).get("sockets") or []
            if isinstance(item, dict) and str(item.get("name") or "").strip()}


OWNED_OUT = "graph.out"                   # свой «Выход» графа попытки: событие для ноды попытки снаружи


def event_of(kind, out):
    """Событие выхода ноды «Когда»: из её списка, а у ноды попытки её выходы — сокеты «Выхода» графа (graph.out)."""
    if out in kind.events:
        return kind.events[out]
    if kind.name == USED_OFFER and out != TIMEOUT and not out.startswith("fork:") and data_out(kind, out) is None:
        return "offer.used"                         # кнопки окна b1, b2…
    return OWNED_OUT if kind.owned and out != TIMEOUT else None


def resolve(kind, data, value):
    """@T и @list — по «Типу элементов» ноды (по умолчанию текст)."""
    if value not in (ELEMENT, OF_LIST, MANY + ELEMENT) or not kind.typed:
        return value
    element = (data or {}).get(kind.typed) or "text"
    element = element if element in ELEMENTS else "text"
    return {ELEMENT: element, OF_LIST: LIST + element}.get(value, MANY + element)


def sock_type(kind, data, side, name, iface=None):
    return resolve(kind, data, _sock_type(kind, data, side, name, iface))


def _sock_type(kind, data, side, name, iface=None):
    """Тип сокета ноды: у групп и сценариев — по интерфейсу, у «Входа»/«Выхода» — по списку, иначе событие или тип выхода данных."""
    if kind.name in BOXES:
        return ((iface or {}).get("in_types" if side == "in" else "out_types") or {}).get(name, EVENT)
    if kind.name in ("group_in", "group_out"):
        return socket_types(data).get(name, EVENT)
    if side == "out":
        if kind.owned and name in ((iface or {}).get("out_types") or {}):
            return iface["out_types"][name]
        if kind.name == USED_OFFER and name.startswith("fork:"):
            return "text"
        if name in kind.plural:
            mode, values = kind.plural[name]
            field_ = next((f for f in kind.fields if f.name == mode), None)
            chosen = (data or {}).get(mode) or (field_.options[0][0] if field_ and field_.options else "")
            return LIST + out_type(kind, name) if chosen in values else out_type(kind, name)
        return out_type(kind, name)
    if name.startswith("f:"):
        found = next((f for f in kind.fields if f.name == name[2:]), None)
        if found is None and is_row(kind, name[2:]):
            return kind.grow.type
        return field_type(found) if found else ""
    return kind.in_types.get(name, EVENT)


def sockets(kind, data, side, iface=None):
    """Имена сокетов ноды с её данными: side "in" или "out". У группы и сценария — по их интерфейсу iface
    {"inputs": [имя], "outputs": [имя]} (его даёт тот, кто знает определение группы или другой граф)."""
    if kind.name in BOXES:
        return list((iface or {}).get("inputs" if side == "in" else "outputs") or [])
    names = list(kind.ins if side == "in" else [sock.name for sock in kind.outs if sock.name != REF])
    if side == "out" and kind.name == USED_OFFER and iface is not None:
        names = list(iface.get("outputs") or [])            # по сущности: Верно/Неверно, кнопки, «Нажата», развилки
    for many in kind.many:
        if many.side == side:
            if not many.prefix:
                names += [name for name, _ in named(data, many.field)]
            else:
                names += [f"{many.prefix}{n}" for n in range(1, len(_count(data, many.field)) + 1)]
    if side == "out":
        if kind.owned:
            names += list((iface or {}).get("outputs") or [])
        names += [sock.name for sock in kind.tail if active(kind, data, sock.name)]
        names += [sock.name for sock in DATA_OUTS.get(kind.name, ()) if _out_on(kind, data, sock.name)]
        if kind.group in NOUNS and not kind.start_only:
            names.append(TIMEOUT)                    # есть только у ждущей ноды (со входом)
    return names


SPACES = ("Машина", "Учётка", "Сессия", "Сетевой ресурс", "Терминал", "Объект", "Размещение", "Слой", "Игрок", "Экран", "Персонаж", "Почта", "Эфир", "Форум", "Новости",
          "Момент", "Тег", "Счётчик")                # порядок пространств в меню (как у «Когда»)


# события: игрок руками их не вызовет — время, сигналы, автор, изменения от сценария
for _name in ("manual", "signal", "on:machine.status", "on:moment.status", "on:tag", "on:count", "on:count.threshold", "on:time", "on:schedule",
              "on:layer.added", "on:air.station"):
    KINDS[_name] = replace(KINDS[_name], group=HAPPEN)
    DATA_OUTS[_name] = tuple(sock for sock in DATA_OUTS.get(_name, ()) if sock.name != "player")      # игрок их не вызывает: выхода «Игрок» нет
DATA_OUTS["manual"] = (Sock("author", "Автор", "text", "author"),)          # кто из авторов нажал кнопку


def _menu_order(kind):
    space = kind.label.split(": ")[0] if ": " in kind.label else ""
    return list(GROUPS).index(kind.group), SPACES.index(space) if kind.group == ACTION and space in SPACES else 0


# теги и счётчики: «Владелец» одним сокетом (игрок, персонаж, машина, сервер, объект) — владелец по типу провода
_OWNED_BY = {"player": ("player", "who"), "character": ("character", "character"), "machine": ("machine", "machine"), "server": ("server", "server"),
             "item": ("object", "item"), "account": ("account", "account")}
_THINGS = ("who", "character", "machine", "server", "item", "account")


_OWNER_SET = ("owner", "who", "character", "machine", "server", "item", "account", "scope", "for")


def _with_owner(name, many):
    """«Владелец» — только провод (игрок, персонаж, машина, сервер, объект, учётка) и «Чьё»: общий или для игрока.
    Без владельца: общий — мир, для игрока — игрок. С вещью: общий — её, для игрока — пары «вещь + игрок». Игрок-владелец — его."""
    kind = KINDS[name]
    at = next(i for i, f in enumerate(kind.fields) if f.name == "owner")
    rest = [f for f in kind.fields if f.name not in _OWNER_SET]
    owner = (Field("thing", "Владелец", (MANY if many else "") + "player|character|machine|server|object|account", "нет — мир или игрок"),
             Field("scope", "Чьё", "select", "", False, (("shared", "общий"), ("player", "для игрока"))),
             Field("for", "Игрок", "player", "инициатор"))
    when = {key: rule for key, rule in kind.when.items() if key not in _OWNER_SET}
    when["for"] = ("scope", ("player",))
    KINDS[name] = replace(kind, fields=tuple(rest[:at]) + owner + tuple(rest[at:]), when=when, infers={"thing": ("owner", _OWNED_BY)})


def owner_defaults(data):
    """Без провода во «Владелец» (и без прежнего выбора owner): общий — мир, для игрока — игрок из «Игрок» (пусто — инициатор)."""
    if (data or {}).get("owner"):
        return data
    data = dict(data or {})
    if data.get("scope") == "player":
        data["owner"], data["who"] = "player", data.get("for") or data.get("who")
    else:
        data["owner"] = "world"
    return data


for _name in ("ent:tag", "ent:count"):
    _with_owner(_name, False)
for _name in ("on:tag", "on:count", "on:count.threshold", "act:tag", "act:count"):
    _with_owner(_name, True)
# действия над вещами мира: одно или список — с каждой
for _name, _fields in (("act:machine.status", ("host",)), ("act:moment", ("moment",))):
    KINDS[_name] = replace(KINDS[_name], fields=tuple(replace(f, kind=MANY + f.kind) if f.name in _fields else f for f in KINDS[_name].fields),
                           in_types={"in": EVENT + "|bool"})      # «Когда» — поток или условие: верно — сделать, стало ложно — отменить (UNDO)

# «Пока» и действия с условием во «Когда»: условие пересчитывается на событиях и тиках, срабатывает смена
WHILE_EVENT = "@while"
BIND = "@bind"
UNDO = {"act:machine.status": {"stop": "start", "maintenance": "start"}, "act:moment": {"start": "end", "end": "start"}}
register(Kind("while", "Пока", NOUN, "{condition}", (
    Field("condition", "Условие", "condition", "tag:vip; или провод да/нет", True),
    Field("scope", "Для кого", "select", "", False, (("player", "каждого игрока"), ("world", "мир"))),
), (Sock("true", "Стало верно"), Sock("false", "Стало ложно")), ins=(), events={"true": WHILE_EVENT, "false": WHILE_EVENT}, start_only=True))
DATA_OUTS["while"] = (Sock("player", "Игрок", "player", "@player"),)
KINDS["do:net_node"] = replace(KINDS["do:net_node"], fields=tuple(replace(f, kind="server") if f.name == "address" else f for f in KINDS["do:net_node"].fields))


def inferred(kind, data, types):
    """Поля, которые задаёт тип провода (Kind.infers): types — {поле: тип того, что пришло}. Возвращает дополненные данные."""
    if not kind.infers:
        return data
    data = dict(data)
    for name, (mode, by) in kind.infers.items():
        mult, bases = split_type(types.get(name) or "")
        found = by.get(bases[0]) if name in types else None
        if found is not None:
            data[found[1]] = data.get(name)
            data[mode] = found[0]
    return owner_defaults(data) if "thing" in kind.infers else data


def catalog():
    """Виды нод для Студии."""
    def fields(items, sockets=True):
        return [{"name": f.name, "label": f.label, "kind": f.kind, "placeholder": f.placeholder, "required": f.required,
                 "options": [{"value": v, "label": label} for v, label in f.options], "socket": field_type(f) if sockets else ""} for f in items]

    return {
        "groups": [{"name": name, "label": label} for name, label in GROUPS.items()],
        "start_fields": fields(START_FIELDS, False),
        "wait_fields": fields(WAIT_FIELDS, False),
        "types": list(TYPES),
        "socket_help": SOCKET_HELP,
        "kinds": [{
            "name": k.name, "label": k.label, "group": k.group, "subgroup": k.subgroup, "summary": k.summary, "fields": fields(k.fields),
            "ins": list(k.ins), "in_types": dict(k.in_types), "outs": [{"name": s.name, "label": s.label, "type": EVENT} for s in k.outs if s.name != REF]
            + [{"name": s.name, "label": s.label, "type": s.type} for s in DATA_OUTS.get(k.name, ())],
            "many": [{"side": m.side, "field": m.field, "prefix": m.prefix, "label": m.label} for m in k.many],
            "tail": [{"name": s.name, "label": s.label, "type": EVENT} for s in k.tail],
            "ref": k.ref[0] if k.ref else "", "start_only": k.start_only, "help": HELP.get(k.name, ""), "title": k.title,
            "grow": {"field": k.grow.field, "prefix": k.grow.prefix, "type": k.grow.type, "named": k.grow.named, "min": k.grow.min,
                     "single": list(k.grow.single), "needs": k.grow.needs} if k.grow else None,
            "when": [{"field": name, "mode": mode, "values": list(values)} for name, rule in k.when.items()
                     for mode, values in ([rule] if isinstance(rule[0], str) else rule)],
            "hidden": k.hidden, "owned": k.owned, "typed": k.typed, "covers": {name: list(hid) for name, hid in k.covers.items()},
            "follows": dict(k.follows), "titled": dict(k.titled),
            "inline": {name: {"switch": switch, "drop": list(drop)} for name, (switch, drop) in k.inline.items()},
            "plural": {name: {"mode": mode, "values": list(values)} for name, (mode, values) in k.plural.items()},
            "outs_when": {name: {"mode": mode, "values": list(values)} for name, (mode, values) in k.outs_when.items()},
            "types_from": list(k.types_from),
            "infers": {name: {"mode": mode, "by": {t: {"value": v, "field": f} for t, (v, f) in by.items()}} for name, (mode, by) in k.infers.items()},
        } for k in sorted(KINDS.values(), key=_menu_order)],
    }
