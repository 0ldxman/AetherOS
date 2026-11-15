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
GROUPS = {ENTITY: "Сущности", NOUN: "Когда", FLOW: "Ход", DATA: "Данные", ACTION: "Действия", STRUCT: "Сценарии и группы", SERVICE: "Служебные"}

# Типы сокетов. event — «случилось» (по нему идёт ход), остальное — данные: читаются в момент, когда нода выполняется.
EVENT = "event"
TYPES = ("event", "bool", "text", "number", "item", "placement", "layer", "machine", "server", "character", "section", "moment", "player", "flag",
         "world_flag", "counter")
TYPE_LABELS = {"event": "событие", "bool": "да/нет", "text": "текст", "number": "число", "item": "объект", "placement": "размещение", "layer": "слой", "machine": "машину",
               "server": "сервер", "character": "персонажа", "section": "раздел", "moment": "момент", "player": "игрока",
               "flag": "метку игрока", "world_flag": "метку мира", "counter": "счётчик"}
THINGS = ("item", "placement", "layer", "machine", "server", "character", "section", "moment", "player", "flag", "world_flag", "counter")

# списки: «list:<тип элемента>»; «list:any» — вход, которому подходит любой список (количество)
ELEMENTS = {"text": "Текст", "number": "Число", "bool": "Да/нет", "item": "Объект", "placement": "Размещение", "layer": "Слой", "machine": "Машина", "server": "Сервер",
            "character": "Персонаж", "section": "Раздел", "moment": "Момент", "player": "Игрок"}
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
               "counter": "counter", "moment": "moment", "machine": "machine", "server": "server", "player": "player", "layer": "layer", "placement": "placement"}      # вид поля -> тип его входа; нет в списке — параметр без входа


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
GLOBAL_EVENTS = frozenset({"world.flag", "world.counter", "moment.started", "moment.ended", "machine.stopped", "machine.started"})   # будят всех ждущих            # ноды-обёртки: сокеты берутся из их «Входа» и «Выхода»
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
    """Событие случилось с размещением wanted («игрок@машина:/путь»; без «игрок@» — у любого игрока)?"""
    head, _, want_path = str(wanted or "").strip().partition(":")
    owner, _, host = head.rpartition("@")
    if not path or want_path != path or not _same(host, event.host):
        return False
    return not owner or (event.user is not None and _same(owner, event.user.get_username()))


# ---------- существительные ----------

START_FIELDS = (
    Field("repeat", "Запускать", "select", "", False, (("once", "один раз за игру"), ("end", "снова после конца"), ("always", "каждый раз"))),
)
WAIT_FIELDS = (
    Field("past", "Засчитать, если уже было", "bool"),
    Field("own", "Только игрок хода", "bool"),
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


THINGS_OF = ("character", "machine", "server", "object")
OWNER_WHEN = {"who": ("owner", ("player",)), "character": ("owner", ("character",)), "machine": ("owner", ("machine",)),
              "server": ("owner", ("server",)), "item": ("owner", ("object",)), "scope": ("owner", THINGS_OF),
              "for": (("owner", THINGS_OF), ("scope", ("player",)))}
_MACHINE = Field("machine", "Машина", "many:machine", "любая")              # фильтры событий: одно или список — подходит любой
_OBJECT = Field("item", "Объект", "many:object", "любой")
_PATH = Field("path", "Путь", "text", "любой; можно *")
_HOST_OUT = Sock("machine", "Машина", "machine", "host")
_LOGIN_OUT = Sock("login", "Учётка", "text", "login")


_when("on:machine.status", "Машина: Статус изменён", (_MACHINE,), (Sock("stopped", "Остановлена"), Sock("started", "Запущена")),
      {"stopped": "machine.stopped", "started": "machine.started"}, _match(machine=("host", "thing")), (_HOST_OUT,), "{machine}")
_when("on:terminal.command", "Терминал: Введена команда",
      (_MACHINE, Field("command", "Команда", "text", "любая; можно *"), Field("args", "Аргументы", "text", "любые; можно *")),
      (Sock("run", "Введена"),), {"run": "command.run"}, _match(machine=("host", "thing"), command=("command", "glob"), args=("args", "glob")),
      (_HOST_OUT, _LOGIN_OUT, Sock("command", "Команда", "text", "command"), Sock("args", "Аргументы", "text", "args")), "{command} {args}")
_OBJECT_MATCH = _match(item=("item", "item"), path=("path", "glob"), machine=("host", "thing"))
_PLACE_OUTS = (Sock("placement", "Размещение", "placement", "placement"), _LOGIN_OUT)       # объект, путь, машина — у ноды «Размещение»
_OBJECT_OUTS = (Sock("placement", "Размещение", "placement", "placement"), Sock("item", "Объект", "item", "item"), Sock("path", "Путь", "text", "path"),
                _HOST_OUT, _LOGIN_OUT)
for _name, _label, _out, _event in (("viewed", "Просмотрен", "Открыл", "file.read"), ("deleted", "Удалён", "Удалил", "file.deleted"),
                                    ("restored", "Восстановлен", "Вернул из корзины", "file.restored"), ("changed", "Изменён", "Сохранил правку", "file.changed")):
    _when(f"on:object.{_name}", f"Объект: {_label}", (_OBJECT, _PATH, _MACHINE), (Sock(_name, _out),), {_name: _event}, _OBJECT_MATCH, _OBJECT_OUTS,
          "{item} {path}")
_when("on:object.got", "Объект: Получен",
      (_OBJECT, Field("via", "Откуда", "select", "", False, (("any", "любым путём"), ("archive", "из письма или архива"), ("forum", "с форума"),
                                                             ("net", "скачан с сервера"), ("xfer", "перенесён с машины"), ("join", "собран из частей"),
                                                             ("key", "ключ в секретах"), ("scenario", "выдан сценарием"))),
       _PATH, _MACHINE),
      (Sock("got", "Получен"),), {"got": "object.got"}, _match(item=("item", "item"), via=("via", "via"), path=("path", "glob"), machine=("host", "thing")),
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
_when("on:layer.changed", "Слой: Изменено",
      (Field("layer", "Слой", "many:layer|placement", "любой"), _OBJECT, Field("type", "Тип", "select", "", False, _layer_types_any())),
      (Sock("removed", "Снят"), Sock("attempt", "Неверная попытка"), Sock("failed", "Попытки кончились"), Sock("added", "Добавлен")),
      {"removed": "layer.removed", "attempt": "layer.attempt", "failed": "layer.failed", "added": "layer.added"},
      _match(layer=("path", "layer"), item=("item", "item"), type=("layer", "same")),
      (Sock("layer", "Слой", "layer", "layer_key"), _LOGIN_OUT, Sock("given", "Ввод игрока", "text", "given")),        # остальное — у «Слоя» и «Размещения»
      "{type} {item}", covers={"layer": ("item",)})
for _name in ("viewed", "deleted", "restored", "changed"):                 # старые: теперь «Размещение: …»
    KINDS[f"on:object.{_name}"] = replace(KINDS[f"on:object.{_name}"], hidden=True)


def _mail(data, out, event):
    return (event.data or {}).get("channel") == "mail" and _match(character=("character", "thing"), text=("text", "glob"))(data, out, event)


_when("on:player.mail", "Игрок: Отправил письмо", (Field("character", "Персонаж", "many:character", "любой"), Field("text", "Текст", "text", "любой; можно *")),
      (Sock("sent", "Отправил"),), {"sent": "character.wrote"}, _mail,
      (Sock("character", "Персонаж", "character", "character"), Sock("text", "Текст", "text", "text")), "{character}")
_when("on:player.air", "Игрок: Отправил в эфир", (Field("freq", "Частота, МГц", "text", "любая"), Field("text", "Текст", "text", "любой; можно *")),
      (Sock("sent", "Отправил"),), {"sent": "air.sent"}, _match(freq=("freq", "freq"), text=("text", "glob")),
      (Sock("freq", "Частота", "text", "freq"), Sock("text", "Текст", "text", "text")), "{freq}")
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


_value_when("on:tag", "Тег: Изменение", (Sock("set", "Поставлен"), Sock("unset", "Снят")), {"set": "value.tag", "unset": "value.tag"}, _tag, ())
_value_when("on:count", "Счётчик: Изменение", (Sock("changed", "Изменился"),), {"changed": "value.count"}, _count,
            (Sock("value", "Значение", "number", "value"), Sock("delta", "Разница", "number", "delta")))
_value_when("on:count.threshold", "Счётчик: Порог", (Sock("up", "Дошёл"), Sock("down", "Ушёл ниже")), {"up": "value.count", "down": "value.count"},
            _threshold, (Sock("value", "Значение", "number", "value"),), (Field("threshold", "Порог", "number", "", True),))
_when("on:time", "Время: В момент",
      (Field("date", "Дата (игровая)", "text", "2031-05-14", True), Field("at", "Время (игровое, ЧЧ:ММ)", "clock", "21:00", True),
       Field("scope", "Для кого", "select", "", False, (("world", "мир"), ("each", "каждый игрок")))),
      (Sock("fire", "Наступило"),), {"fire": TIME_EVENT}, None, (), "{date} {at}", start_only=True)
_when("on:schedule", "Время: По расписанию",
      (Field("mode", "Как часто", "select", "", False, (("daily", "каждый день"), ("weekly", "по дням недели"), ("every", "каждые N минут"))),
       Field("at", "Время (игровое, ЧЧ:ММ)", "clock", "21:00"), Field("days", "Дни недели", "text", "пн, ср, пт"),
       Field("minutes", "Каждые, мин (игровые)", "number", "60"),
       Field("scope", "Для кого", "select", "", False, (("world", "мир"), ("each", "каждый игрок")))),
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
_SERVER_OUTS = (Sock("server", "Сервер", "server", "address"), Sock("path", "Путь", "text", "path"), _HOST_OUT, _LOGIN_OUT)
_when("attempt:server", "Попытка", (), (Sock("go", "Попытка"),), {"go": "@attempt"}, None, _SERVER_OUTS, start_only=True)
KINDS["attempt:server"] = replace(KINDS["attempt:server"], ins=(), hidden=True)
for _kind, _label in (("net.request", "Сетевой сервер: Попытка запроса"), ("net.download", "Сетевой сервер: Попытка скачивания")):
    register(Kind(f"try:{_kind}", _label, NOUN, "{server}", (Field("server", "Сервер", "server", "", True),), (),
                  match=_owned_match(_kind), owned=_kind))
    DATA_OUTS[f"try:{_kind}"] = ()


# ---------- ход ----------

register(Kind("wait", "Ждать", FLOW, "{mode}",
              (Field("mode", "Чего ждать", "select", "", False, (("delay", "время"), ("until", "до времени"), ("condition", "пока условие"))),
               Field("minutes", "Минут", "number", "5"), Field("at", "До (игровое, ЧЧ:ММ)", "clock", "21:00"),
               Field("condition", "Условие", "condition"), Field("timeout", "Таймаут, мин", "number", "без таймаута"),
               Field("real", "Реальное время вместо игрового", "bool")),
              (Sock("next", "Дальше"), Sock(TIMEOUT, "Таймаут"))))
register(Kind("check", "Условие", FLOW, "{condition}", (Field("condition", "Условие", "condition", "", True),),
              (Sock("yes", "Да"), Sock("no", "Нет"))))
register(Kind("choose", "Выбор", FLOW, "", (Field("rows", "Если", "rows"),),
              many=(Many("out", "rows", "r", "{label}"),), tail=(Sock("else", "Иначе"),)))
register(Kind("random", "Случайно", FLOW, "", (Field("branches", "Веса веток", "weights"),),
              many=(Many("out", "branches", "b", "Ветка {n}"),)))
register(Kind("turns", "По очереди", FLOW, "{count}", (Field("count", "Сколько веток", "number", "2"),),
              many=(Many("out", "count", "b", "Ветка {n}"),)))
register(Kind("first", "Первые в мире", FLOW, "первые {count}", (Field("count", "Сколько первых", "number", "1"),),
              (Sock("pass", "Успел"), Sock("late", "Опоздал"))))
register(Kind("once", "Однажды", FLOW, "{per}", (Field("per", "Для кого", "select", "", False, (("game", "за игру"), ("player", "на каждого игрока"))),),
              (Sock("pass", "Впервые"), Sock("again", "Уже было"))))
register(Kind("all", "Все из", FLOW, "{count}", (Field("count", "Сколько входов", "number", "2"),),
              (Sock("next", "Дальше"),), ins=(), many=(Many("in", "count", "i", "Вход {n}"),)))
register(Kind("race", "Первое из", FLOW, "{count}", (Field("count", "Сколько входов", "number", "2"),),
              ins=(), many=(Many("in", "count", "i", "Вход {n}"), Many("out", "count", "o", "Первым {n}"))))
register(Kind("end", "Конец", FLOW, "{outcome}",
              (Field("outcome", "Исход", "select", "", False, (("passed", "прошёл"), ("failed", "провалил"), ("aborted", "прервано"))),)))
register(Kind("foreach", "Для каждого", FLOW, "", (Field("of", "Тип элементов", "select", "", False, tuple(ELEMENTS.items())),
                                                    Field("list", "Список", OF_LIST)),
              (Sock("each", "Каждый"), Sock("done", "Готово")), typed="of"))
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
LEGACY = {"flag", "unflag", "world_flag", "world_unflag", "world_count", "player_count", "character_tag"}   # теперь «Тег» и «Счётчик»


# действия по пространствам, как у «Когда»: одно действие движка — подпись; несколько — нода с выбором, заголовок по выбору
RENAMED = {
    "net_node": "Сетевой сервер: Изменить узел", "file_delete": "Объект: Удалить у игрока", "kick": "Игрок: Выбросить из сессии",
    "notify": "Экран: Уведомление", "ticker": "Экран: Бегущая строка", "windows": "Экран: Окна ошибок", "open_window": "Экран: Окно с адресом",
    "blackout": "Экран: Чёрный экран", "scene": "Экран: Сцена", "air": "Эфир: Передать", "news": "Новости: Опубликовать",
}
_OWNER = ("owner", "who", "character", "machine", "server", "item", "scope", "for", "name")
CHOICES = (
    ("machine.status", "Машина: Изменить статус", (("stop", "Остановить", "machine_power", {"state": "stop"}, ("host",)),
                                                   ("start", "Запустить", "machine_power", {"state": "start"}, ("host",)),
                                                   ("reboot", "Перезагрузить", "machine_power", {"state": "reboot"}, ("host", "minutes")))),
    ("account", "Учётка: Изменить", (("block", "Заблокировать", "account", {}, ("host", "login", "scope", "block", "text")),
                                     ("unblock", "Снять блокировку", "account", {"unblock": True}, ("host", "login", "scope")),
                                     ("password", "Сменить пароль", "account", {}, ("host", "login", "password")))),
    ("object.give", "Объект: Выдать", (("path", "В путь", "file", {}, ("item", "path")), ("secrets", "В секреты (ключ)", "key", {}, ("slug",)))),
    ("object.change", "Объект: Изменить у игрока", (("replace", "Подменить", "file_change", {"mode": "replace"}, ("path", "item")),
                                                   ("move", "Переместить", "file_change", {"mode": "move"}, ("path", "target")))),
    ("layer.change", "Слой объекта: Изменить", (("remove", "Снять верхний", "layer_remove", {}, ("path",)),
                                                ("reset", "Вернуть все", "file_change", {"mode": "reset"}, ("path",)))),
    ("terminal", "Терминал: Вывести", (("text", "Текст", "terminal_text", {}, ("text",)), ("scene", "Сцена", "terminal_scene", {}, ("scene",)))),
    ("mail", "Почта: Прислать письмо", (("player", "Игроку", "letter", {}, ("item", "delay")),
                                       ("all", "Всем", "letter_all", {}, ("item", "machines", "systems")))),
    ("forum", "Форум: Написать", (("new", "Новая тема", "forum", {"mode": "new"}, ("section", "character", "title", "text")),
                                  ("append", "Ответ в тему", "forum", {"mode": "append"}, ("section", "character", "title", "text")))),
    ("moment", "Момент: Изменить статус", (("start", "Начать", "moment_start", {}, ("moment",)), ("end", "Закончить", "moment_end", {}, ("moment",)))),
    ("tag", "Тег: Изменить", (("on", "Поставить", "tag", {"mode": "on"}, _OWNER), ("off", "Снять", "tag", {"mode": "off"}, _OWNER))),
    ("count", "Счётчик: Изменить", (("add", "Прибавить", "count", {"mode": "add"}, _OWNER + ("delta",)),
                                    ("set", "Задать", "count", {"mode": "set"}, _OWNER + ("value",)))),
)
CHOSEN = {spec for _, _, variants in CHOICES for _, _, spec, _, _ in variants}


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
                  title="variant", when=when,
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
                      hidden=spec.name in LEGACY or spec.name in CHOSEN))
    for key, label, variants in CHOICES:
        _choice(key, label, variants)


_actions()

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
    Field("path", "Путь", "path", "/home/{login}/note.txt; ключ — пусто: в секреты"), Field("player", "Игрок", "player", "игрок хода"),
    Field("item", "Объект", "object", "нет — свой файл с текстом"), Field("text", "Текст", "textarea", "подстановки {host}, {login}, {path}…"),
), _ACT_OUTS, covers={"placement": ("machine", "path", "player"), "item": ("text",)}, titled={"item": "Размещение: Добавить"},
    follows={"placement": "placement"}))
DATA_OUTS["act:placement.create"] = (Sock("placement", "Размещение", "many:placement"),)
for _old in ("act:object.give", "act:object.change", "do:file_delete"):     # теперь «Размещение: Создать / Изменить»
    KINDS[_old] = replace(KINDS[_old], hidden=True)
register(Kind("act:layer", "Слой: Изменить", ACTION, "{layer}", (
    Field("variant", "Действие", "select", "", False, (("remove", "Снять"), ("quiet", "Снять тихо"), ("attempts", "Сбросить попытки"))),
    Field("layer", "Слой", "many:layer|placement", "слой или размещение (его верхний слой)", True),
), _ACT_OUTS, title="variant", follows={"layer": "layer"}))
DATA_OUTS["act:layer"] = (Sock("layer", "Слой", "many:layer"),)
KINDS["act:layer.change"] = replace(KINDS["act:layer.change"], hidden=True)                # теперь «Слой: Изменить»
PLACEMENT_ACTS = ("act:placement", "act:placement.create", "act:layer")


# ---------- пояснения (подсказки на холсте, как в Blender) ----------

HELP = {
    "act:placement": "Что-то сделать с файлом игрока: перенести (путь, новое имя или папка/), подменить объект, удалить в корзину или насовсем, "
                     "вернуть из корзины, добавить слой защиты поверх (тип и параметры как в описании), вернуть слои как в описании. "
                     "На вход — одно размещение или список: с каждым. «Размещение» на выходе — где файл теперь.",
    "act:placement.create": "Создать файл игроку: с объектом — «Добавить» (ключ без пути — в папку секретов), без объекта — свой файл с текстом. "
                            "Куда — размещение или Машина + Путь (+ Игрок, пусто — игрок хода).",
    "manual": "Кнопка автора: запустить ход с игроком или без (мир) из панели ноды. Только старт.",
    "try:machine": "Вход на выбранную машину. Tab — граф входа этой машины: от «Попытки» до «Ответить», без ожиданий. "
                   "Выходы ноды — сокеты «Выхода» внутри графа: события и данные.",
    "attempt:machine": "Игрок пытается войти: подробности попытки. Дальше проверки и действия, конец — «Ответить».",
    "on:machine.status": "Машину остановили или запустили (для всех). Пустая машина — любая.",
    "on:terminal.command": "Игрок ввёл команду в терминале. Команда и аргументы понимают *.",
    "on:object.viewed": "Игрок открыл файл. Фильтры: объект, путь (*), машина; пусто — любой.",
    "on:object.deleted": "Игрок удалил файл (в корзину).", "on:object.restored": "Игрок вернул файл из корзины.",
    "on:object.changed": "Игрок сохранил правку текста файла.",
    "on:placement.changed": "Файл игрока изменился: отредактирован, перенесён, удалён в корзину, возвращён, стёрт насовсем. "
                            "Провод «Размещение» — следить за этим файлом, иначе фильтры (объект — любая его копия, путь *, машина). "
                            "«Было» — где файл был, «Размещение» — где он теперь (после удаления — в корзине). "
                            "Ждущая нода сама идёт за файлом, если он переехал.",
    "on:placement.opened": "Игрок открыл файл. Провод «Размещение» — этот файл; иначе фильтры: объект, путь (*), машина.",
    "on:placement.appeared": "У игрока появился новый файл: сделал сам (вырезка, подпись, текст из архива) или скопировал. "
                             "Объект, впервые попавший к игроку, — «Объект: Получен».",
    "on:object.got": "Объект лёг игроку: из письма или архива, с форума, с сервера, с другой машины, собран из частей, ключ, выдан сценарием.",
    "on:player.mail": "Игрок написал персонажу письмо.", "on:player.air": "Игрок передал в эфир на частоте.",
    "on:moment.status": "Момент мира начался или кончился.",
    "on:tag": "Тег владельца поставили или сняли. Владелец и «чьё» — как у ноды «Тег».",
    "on:count": "Счётчик владельца изменился: выходы — новое значение и разница.",
    "on:count.threshold": "Счётчик перешёл порог: «Дошёл» — снизу вверх, «Ушёл ниже» — сверху вниз.",
    "on:time": "Один раз в игровую дату и время. Для мира или для каждого игрока.",
    "on:schedule": "По игровому времени: каждый день в ЧЧ:ММ, по дням недели или каждые N минут.",
    "signal": "Сигнал от «Послать сигнал» с тем же именем: связывает сценарии без проводов.",
    "wait": "Ждать время, до времени (ЧЧ:ММ) или пока условие не станет верным. Время игровое, если не отмечено «реальное».",
    "check": "Проверить факты игрока (ключи, tag:, count:, world:) и пойти в «Да» или «Нет».",
    "choose": "Строки «если»: первая верная ведёт в свой выход, иначе «Иначе».",
    "random": "Случайная ветка; чем больше вес, тем чаще.",
    "turns": "По очереди: каждый следующий игрок идёт в следующую ветку (раздать разные части).",
    "first": "Первые N игроков в мире идут в «Успел», остальные — в «Опоздал» (first decoded by).",
    "once": "Первый проход — «Впервые», дальше — «Уже было». За игру — один на всех; на каждого игрока — первый проход игрока хода.",
    "all": "Дальше, когда пришли все входы, в любом порядке.",
    "race": "Дальше по первому пришедшему входу; остальные ожидания, ведущие сюда, снимаются.",
    "end": "Прохождение закончено с исходом; все ждущие ветки снимаются.",
    "answer": "Ответ в графе попытки (у машины, сервера, слоя): впустить, отказать, заблокировать или как обычно — решают поля вещи.",
    "reroute": "Точка излома провода. Ничего не делает.",
    "group": "Группа нод (Ctrl+G). Tab — войти. Сокеты — её «Вход» и «Выход».",
    "group_in": "Вход группы или сценария: сокеты слева у ноды группы; сюда приходит «Запустить сценарий».",
    "group_out": "Выход группы или сценария: сокеты справа у ноды группы.",
    "scenario": "Другой сценарий целиком, как группа. Идёт в ходах этого сценария; его старты здесь не срабатывают.",
    "launch": "Запустить другой сценарий: новый ход с игроком этого хода, не дожидаясь его.",
    "send_signal": "Послать сигнал: будит ноды «Сигнал» с тем же именем — с игроком хода или у всех.",
    "stage": "Отметка хода: счётчик «прошли» на холсте.",
    "note": "Заметка на холсте. Не исполняется.",
    "frame": "Рамка вокруг нод. Не исполняется.",
    "text": "Текст: значение для входов.", "number": "Число: значение для входов.", "boolean": "Да/нет: значение для входов.",
    "template": "Склеить текст: {имя} в шаблоне заменяется значением подстановки с этим именем. Заполнили подстановку — появляется следующая.",
    "compare": "Сравнить A и B: числа — как числа, остальное — как текст без учёта регистра. «По образцу» понимает *.",
    "logic": "И — все входы да; Или — хоть один да; Не — наоборот; Исключающее или — ровно один да. Подключили вход — появляется следующий.",
    "fact": "Условие на факты игрока хода: ключи, tag:, count:, world:. Верно или нет.",
    "math": "Посчитать A и B. «Случайное» — целое от A до B; округление, модуль и смена знака берут только A.",
    "read": "Прочитать сейчас: счётчик или метку мира, счётчик или метку игрока хода.",
    "ent:machine": "Машина: выбрать в ноде, получить проводом или найти по хосту/имени из текста. Свойства — как сейчас.",
    "ent:server": "Сетевой сервер (nreq, nget): по адресу.", "ent:object": "Объект библиотеки — содержимое, общее для всех; по слагу или названию.",
    "ent:character": "Персонаж: по коду или имени.", "ent:section": "Раздел форума: по номеру или названию.",
    "ent:moment": "Момент мира: по имени или названию; «Идёт» — сейчас ли он.",
    "ent:player": "Игрок: пусто — игрок хода, иначе по логину.",
    "list.make": "Собрать список из входов: подключили последний — появился следующий. Тип элементов выбирается на ноде.",
    "list.count": "Сколько элементов в списке (пустой — 0).",
    "list.item": "Элемент списка: первый, последний или по номеру. «Есть» — нет ли такого (список короче).",
    "list.has": "Есть ли значение в списке (текст — без учёта регистра).",
    "foreach": "Для каждого элемента списка — ветка «Каждый» с данными «Элемент» и «Номер», потом «Готово». В ветке «Каждый» нельзя ждать.",
    "switch": "Если «Если» — да, значение «Да», иначе «Нет». Так выход получает значение по условию.",
    "allowed": "поля вещи пустили (у «как обычно»)", "refused": "поля вещи отказали (у «как обычно»)",
    "ent:tag": "Тег владельца: мира, игрока, персонажа, машины, сервера или объекта; у вещи — общий или свой у игрока.",
    "ent:count": "Счётчик владельца, как у «Тега»; «Подпись» — подпись значения из описания счётчика («2» — «Архив»).",
    "act:tag": "Поставить или снять тег владельца (мир, игрок, вещь; у вещи — общий или для игрока).",
    "act:count": "Прибавить к счётчику владельца или задать его.",
    "act:machine.status": "Остановить, запустить или перезагрузить машину — для всех. Остановленная не находится, сессии обрываются.",
    "act:account": "Учётка: заблокировать на N минут (игроку или всем), снять блокировку, сменить пароль для всех.",
    "act:object.give": "Выдать объект игроку: файлом по пути на учётке события или ключом в папку секретов.",
    "act:object.change": "Файл игрока: подменить объект или переместить.",
    "act:layer.change": "Слои файла игрока: снять верхний (как будто игрок снял сам, хуки срабатывают) или вернуть все.",
    "act:terminal": "Строка или сцена во все открытые терминалы игрока.",
    "act:mail": "Готовое письмо: игроку в ящик учётки события (можно с задержкой) или всем при открытии почты.",
    "act:forum": "Запись на форуме от системы или персонажа: новая тема или ответ в тему с таким заголовком.",
    "act:moment": "Начать или закончить момент мира сейчас.",
    "ent:layer": "Слой файла игрока (провод с «Размещение → Слои» или события слоя): тип, индекс (1 — верхний), снят ли, сколько попыток осталось (-1 — без ограничения), добавлен ли поверх описания, чьё размещение.",
    "on:layer.changed": "Со слоем файла игрока что-то случилось: снят, неверная попытка, попытки кончились, добавлен поверх. Провод «Слой» — этот слой, «Размещение» — любой слой файла; иначе фильтры: объект, тип. Тип, размещение, объект — у ноды «Слой».",
    "act:layer": "Сделать со слоем: снять (как игрок — хуки срабатывают; не верхний — вместе со всем, что над ним), снять тихо (без хуков), "
                 "сбросить попытки. Размещение — его верхний слой.",
    "try:net.request": "Запрос к выбранному серверу (nreq). Tab — граф попытки сервера; выходы — сокеты «Выхода» внутри.",
    "try:net.download": "Скачивание с выбранного сервера (nget). Tab — граф попытки сервера; выходы — сокеты «Выхода» внутри.",
    "attempt:server": "Игрок обращается к серверу: подробности попытки. Дальше проверки и действия, конец — «Ответить».",
    "ent:placement": "Размещение — файл в виде игрока: машина и путь (пусто «Игрок» — игрок хода) или провод «Размещение». "
                     "Свойства — как сейчас: есть ли файл, какой в нём объект, в корзине ли.",
    "find": "Размещения игрока на его машинах: с объектом (пусто — любые файлы), путь по образцу *, вне корзины, в корзине или везде. "
            "Список — «Для каждого» или «Список: …». Перенос и переименование файла его не теряют.",
    "do:flag": "Поставить тег игроку (tag:имя).", "do:unflag": "Снять тег игрока.",
    "do:key": "Положить ключ в папку секретов учётки, на которой случилось событие.",
    "do:file": "Положить объект файлом по пути в учётке игрока.",
    "do:letter": "Прислать готовое письмо в ящик учётки игрока (можно с задержкой).",
    "do:kick": "Выбросить игрока из сессии учётки события.",
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
    "do:file_delete": "Удалить файл у игрока (его копию).",
    "do:file_change": "Изменить файл игрока: подменить объект, переименовать или переместить, вернуть слои.",
    "do:machine_power": "Остановить, запустить или перезагрузить машину — для всех. Остановленная не находится, сессии обрываются.",
    "do:account": "Учётка: заблокировать на N минут (игроку или всем), снять блокировку, новый пароль для всех.",
    "do:net_node": "Узел сервера: новый токен или ответ страницы — для всех.",
    "do:moment_start": "Начать момент мира сейчас.", "do:moment_end": "Закончить момент мира сейчас.",
    "do:character_tag": "Поставить или снять тег персонажа (tag:character:КОД:тег в условиях).",
}

SOCKET_HELP = {
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
    "value": "значение", "player": "игрок хода (имя)", "path": "путь файла из события", "layer": "слой из события",
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
    "server": "сервер",
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

_data("text", "Текст", "{value}", (Field("value", "Текст", "text"),), "text", "Текст")
_data("number", "Число", "{value}", (Field("value", "Число", "number"),), "number", "Число")
_data("boolean", "Да/нет", "{value}", (Field("value", "Да", "bool"),), "bool", "Да/нет")
_data("template", "Текст по шаблону", "{template}",
      (Field("template", "Шаблон", "text", "{игрок} открыл {файл}"), Field("subs", "Подстановки", "hidden")), "text", "Текст",
      grow=Grow("subs", "s", "text", named=True))
_data("compare", "Сравнить", "{op}",
      (Field("a", "A", "text"), Field("op", "Как", "select", "", False, (("eq", "="), ("ne", "≠"), ("gt", ">"), ("ge", "≥"), ("lt", "<"), ("le", "≤"),
                                                                       ("contains", "содержит"), ("like", "по образцу *"))), Field("b", "B", "text")),
      "bool", "Верно")
LOGIC = (("and", "И"), ("or", "Или"), ("not", "Не"), ("xor", "Исключающее или"))
_data("logic", "Логика", "", (Field("op", "Действие", "select", "", False, LOGIC), Field("values", "Входы", "hidden")), "bool", "Да/нет",
      title="op", grow=Grow("values", "v", "bool", min=2, single=("not",)))
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
_OF = Field("of", "Тип элементов", "select", "", False, tuple(ELEMENTS.items()))
_data("list.make", "Список: Собрать", "", (_OF, Field("items", "Элементы", "hidden")), OF_LIST, "Список",
      typed="of", grow=Grow("items", "e", ELEMENT, min=2))
_data("list.count", "Список: Количество", "", (Field("list", "Список", ANY_LIST.replace("list:any", "@any")),), "number", "Количество")
_data("list.item", "Список: Элемент", "",
      (_OF, Field("mode", "Какой", "select", "", False, (("first", "Первый"), ("last", "Последний"), ("number", "По номеру"))),
       Field("list", "Список", OF_LIST), Field("number", "Номер", "number", "1")), ELEMENT, "Элемент",
      typed="of", when={"number": ("mode", ("number",))})
DATA_OUTS["list.item"] += (Sock("found", "Есть", "bool"),)
_data("list.has", "Список: Содержит", "", (_OF, Field("list", "Список", OF_LIST), Field("value", "Значение", MANY + ELEMENT)), "bool", "Содержит",
      typed="of")
_data("switch", "Выбрать значение", "",
      (Field("condition", "Если", "bool"), Field("yes", "Да", "text"), Field("no", "Нет", "text")), "text", "Значение")
KINDS["read"] = replace(KINDS["read"], hidden=True)                 # теперь «Тег» и «Счётчик»


# ---------- сущности: вещь мира и её свойства сейчас (graph/entities.py) ----------

def _entity(name, label, field, outs):
    register(Kind(name, label, ENTITY, "{%s}" % field.name, (field,), ins=()))
    DATA_OUTS[name] = outs


_entity("ent:machine", "Машина", Field("machine", "Машина", "machine"),
        (Sock("value", "Машина", "machine"), Sock("name", "Имя", "text"), Sock("address", "Адрес", "text"),
         Sock("system", "ОС", "text"), Sock("up", "Работает", "bool")))
_entity("ent:server", "Сервер", Field("server", "Сервер", "server"),
        (Sock("value", "Сервер", "server"), Sock("title", "Название", "text")))
_entity("ent:object", "Объект", Field("item", "Объект", "object"),
        (Sock("value", "Объект", "item"), Sock("name", "Название", "text"), Sock("format", "Формат", "text")))
_entity("ent:character", "Персонаж", Field("character", "Персонаж", "character"),
        (Sock("value", "Персонаж", "character"), Sock("name", "Имя", "text"), Sock("callsign", "Позывной", "text"),
         Sock("active", "Активен", "bool")))
_entity("ent:section", "Раздел", Field("section", "Раздел", "section"),
        (Sock("value", "Раздел", "section"), Sock("title", "Название", "text"), Sock("archived", "В архиве", "bool")))
_entity("ent:moment", "Момент", Field("moment", "Момент", "moment"),
        (Sock("value", "Момент", "moment"), Sock("title", "Название", "text"), Sock("running", "Идёт", "bool")))
_entity("ent:player", "Игрок", Field("player", "Игрок", "player", "игрок хода"),
        (Sock("value", "Игрок", "player"), Sock("callsign", "Позывной", "text")))
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
    Field("player", "Игрок", "player", "игрок хода"),
), ins=(), covers={"placement": ("machine", "path", "player")}))
DATA_OUTS["ent:placement"] = (Sock("value", "Размещение", "placement"), Sock("item", "Объект", "item"), Sock("machine", "Машина", "machine"),
                              Sock("path", "Путь", "text"), Sock("name", "Имя", "text"), Sock("exists", "Есть", "bool"),
                              Sock("trash", "В корзине", "bool"), Sock("edited", "Изменён игроком", "bool"), Sock("layers", "Слои", "list:layer"))
register(Kind("find", "Размещение: Найти", ENTITY, "{item} {path}", (
    Field("item", "Объект", "many:object", "любой"), Field("player", "Игрок", "player", "игрок хода"), Field("machine", "Машина", "machine", "любая"),
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
        return out_type(kind, name)
    if name.startswith("f:"):
        found = next((f for f in kind.fields if f.name == name[2:]), None)
        if found is None and is_row(kind, name[2:]):
            return kind.grow.type
        return field_type(found) if found else ""
    return EVENT


def sockets(kind, data, side, iface=None):
    """Имена сокетов ноды с её данными: side "in" или "out". У группы и сценария — по их интерфейсу iface
    {"inputs": [имя], "outputs": [имя]} (его даёт тот, кто знает определение группы или другой граф)."""
    if kind.name in BOXES:
        return list((iface or {}).get("inputs" if side == "in" else "outputs") or [])
    names = list(kind.ins if side == "in" else [sock.name for sock in kind.outs if sock.name != REF])
    for many in kind.many:
        if many.side == side:
            if not many.prefix:
                names += [name for name, _ in named(data, many.field)]
            else:
                names += [f"{many.prefix}{n}" for n in range(1, len(_count(data, many.field)) + 1)]
    if side == "out":
        if kind.owned:
            names += list((iface or {}).get("outputs") or [])
        names += [sock.name for sock in kind.tail]
        names += [sock.name for sock in DATA_OUTS.get(kind.name, ())]
        if kind.group == NOUN and not kind.start_only:
            names.append(TIMEOUT)                    # есть только у ждущей ноды (со входом)
    return names


SPACES = ("Машина", "Учётка", "Сетевой сервер", "Терминал", "Объект", "Размещение", "Слой объекта", "Игрок", "Экран", "Почта", "Эфир", "Форум", "Новости",
          "Момент", "Тег", "Счётчик")                # порядок пространств в меню (как у «Когда»)


def _menu_order(kind):
    space = kind.label.split(": ")[0] if ": " in kind.label else ""
    return list(GROUPS).index(kind.group), SPACES.index(space) if kind.group == ACTION and space in SPACES else 0


# теги и счётчики: «Владелец» одним сокетом (игрок, персонаж, машина, сервер, объект) — владелец по типу провода
_OWNED_BY = {"player": ("player", "who"), "character": ("character", "character"), "machine": ("machine", "machine"), "server": ("server", "server"),
             "item": ("object", "item")}
_THINGS = ("who", "character", "machine", "server", "item")


_OWNER_SET = ("owner", "who", "character", "machine", "server", "item", "scope", "for")


def _with_owner(name, many):
    """«Владелец» — только провод (игрок, персонаж, машина, сервер, объект) и «Чьё»: общий или для игрока.
    Без владельца: общий — мир, для игрока — игрок. С вещью: общий — её, для игрока — пары «вещь + игрок». Игрок-владелец — его."""
    kind = KINDS[name]
    at = next(i for i, f in enumerate(kind.fields) if f.name == "owner")
    rest = [f for f in kind.fields if f.name not in _OWNER_SET]
    owner = (Field("thing", "Владелец", (MANY if many else "") + "player|character|machine|server|object", "нет — мир или игрок"),
             Field("scope", "Чьё", "select", "", False, (("shared", "общий"), ("player", "для игрока"))),
             Field("for", "Игрок", "player", "игрок хода"))
    when = {key: rule for key, rule in kind.when.items() if key not in _OWNER_SET}
    when["for"] = ("scope", ("player",))
    KINDS[name] = replace(kind, fields=tuple(rest[:at]) + owner + tuple(rest[at:]), when=when, infers={"thing": ("owner", _OWNED_BY)})


def owner_defaults(data):
    """Без провода во «Владелец» (и без прежнего выбора owner): общий — мир, для игрока — игрок из «Игрок» (пусто — игрок хода)."""
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
for _name, _fields in (("act:machine.status", ("host",)), ("act:account", ("host",)), ("act:moment", ("moment",))):
    KINDS[_name] = replace(KINDS[_name], fields=tuple(replace(f, kind=MANY + f.kind) if f.name in _fields else f for f in KINDS[_name].fields))
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
            "ins": list(k.ins), "outs": [{"name": s.name, "label": s.label, "type": EVENT} for s in k.outs if s.name != REF]
            + [{"name": s.name, "label": s.label, "type": s.type} for s in DATA_OUTS.get(k.name, ())],
            "many": [{"side": m.side, "field": m.field, "prefix": m.prefix, "label": m.label} for m in k.many],
            "tail": [{"name": s.name, "label": s.label, "type": EVENT} for s in k.tail],
            "ref": k.ref[0] if k.ref else "", "start_only": k.start_only, "help": HELP.get(k.name, ""), "title": k.title,
            "grow": {"field": k.grow.field, "prefix": k.grow.prefix, "type": k.grow.type, "named": k.grow.named, "min": k.grow.min,
                     "single": list(k.grow.single)} if k.grow else None,
            "when": [{"field": name, "mode": mode, "values": list(values)} for name, rule in k.when.items()
                     for mode, values in ([rule] if isinstance(rule[0], str) else rule)],
            "hidden": k.hidden, "owned": k.owned, "typed": k.typed, "covers": {name: list(hid) for name, hid in k.covers.items()},
            "follows": dict(k.follows), "titled": dict(k.titled),
            "infers": {name: {"mode": mode, "by": {t: {"value": v, "field": f} for t, (v, f) in by.items()}} for name, (mode, by) in k.infers.items()},
        } for k in sorted(KINDS.values(), key=_menu_order)],
    }
