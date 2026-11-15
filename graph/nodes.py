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
TYPES = ("event", "bool", "text", "number", "item", "machine", "server", "character", "section", "moment", "player", "flag", "world_flag",
         "counter")
TYPE_LABELS = {"event": "событие", "bool": "да/нет", "text": "текст", "number": "число", "item": "объект", "machine": "машину",
               "server": "сервер", "character": "персонажа", "section": "раздел", "moment": "момент", "player": "игрока",
               "flag": "метку игрока", "world_flag": "метку мира", "counter": "счётчик"}
THINGS = ("item", "machine", "server", "character", "section", "moment", "player", "flag", "world_flag", "counter")
FIELD_TYPES = {"text": "text", "textarea": "text", "path": "text", "clock": "text", "expr": "text", "scene": "text", "station": "text",
               "graph": "text", "number": "number", "bool": "bool", "condition": "bool", "key": "item", "item": "item", "letter": "item",
               "object": "item", "character": "character", "section": "section", "flag": "flag", "world_flag": "world_flag",
               "counter": "counter", "moment": "moment", "machine": "machine", "server": "server", "player": "player"}      # вид поля -> тип его входа; нет в списке — параметр без входа


def field_type(field):
    return FIELD_TYPES.get(field.kind, "")


def compatible(src, dst):
    """Можно ли вести провод из выхода типа src во вход типа dst (как в Blender: число в текст можно, событие в данные нельзя)."""
    if src == dst:
        return True
    if EVENT in (src, dst):
        return False
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
    title: str = ""                     # поле-режим, подпись выбранного варианта — заголовок ноды (как у Math в Blender)
    grow: object = None                 # Grow: растущий список входов
    when: dict = field(default_factory=dict)         # поле -> (поле-режим, значения) или список таких пар: вход есть только в этих режимах
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


# ---------- существительные ----------

START_FIELDS = (
    Field("repeat", "Запускать", "select", "", False, (("once", "один раз на игрока"), ("end", "снова после конца"), ("always", "каждый раз"))),
)
WAIT_FIELDS = (
    Field("past", "Засчитать, если уже было", "bool"),
    Field("anyone", "Событие любого игрока", "bool"),
    Field("timeout", "Таймаут, мин (игровые)", "number", "без таймаута"),
)


def _machine(data, out, event):
    if out in ("stopped", "started"):
        return _same(event.host, data.get("host"))
    return _same(event.host, data.get("host")) and _glob(event.login, data.get("login"))


def _server(data, out, event):
    d = event.data or {}
    from machines.models.net import normalize_address

    if normalize_address(d.get("address", "")) != normalize_address(data.get("address", "")) and \
            normalize_address(d.get("address", "")).split("://")[-1] != normalize_address(data.get("address", "")).split("://")[-1]:
        return False
    return _glob(d.get("path", ""), data.get("path"))


def _command(data, out, event):
    d = event.data or {}
    return _glob(d.get("command", ""), data.get("command")) and _glob(d.get("args", ""), data.get("args"), fold=True) \
        and (not data.get("host") or _same(event.host, data.get("host")))


def _player_counter(data, out, event):
    d = event.data or {}
    if not _same(d.get("counter"), data.get("name")):
        return False
    if out == "changed":
        return True
    try:
        return int(d.get("value") or 0) >= int(data.get("threshold") or 0)
    except (TypeError, ValueError):
        return False


def _file(data, out, event):
    d = event.data or {}
    item = data.get("item")
    if item and not (_same(d.get("item"), item) or _same(d.get("slug"), item)):
        return False
    if not _glob(d.get("path", ""), data.get("path")):
        return False
    if out.startswith("layer_") and not _glob(d.get("layer", ""), data.get("layer")):
        return False
    return bool(item or data.get("path"))


def _character(data, out, event):
    d = event.data or {}
    return _same(d.get("character"), data.get("character")) and d.get("channel") == out and _glob(d.get("text", ""), data.get("text"), fold=True)


def _freq(data, out, event):
    d = event.data or {}
    try:
        same = abs(float(d.get("freq") or 0) - float(str(data.get("freq") or "").replace(",", "."))) < 0.0005
    except ValueError:
        return False
    return same and _glob(d.get("text", ""), data.get("text"), fold=True)


def _section(data, out, event):
    d = event.data or {}
    if str(d.get("section")) != str(data.get("section") or ""):
        return False
    return bool(d.get("new_topic")) == (out == "topic")


def _flag(data, out, event):
    return _same((event.data or {}).get("flag"), data.get("name"))


def _world_flag(data, out, event):
    d = event.data or {}
    return _same(d.get("flag"), data.get("name")) and bool(d.get("on")) == (out == "on")


def _counter(data, out, event):
    d = event.data or {}
    if not _same(d.get("counter"), data.get("name")):
        return False
    if out == "changed":
        return True
    try:
        limit, value, delta = int(data.get("threshold") or 0), int(d.get("value") or 0), int(d.get("delta") or 0)
    except (TypeError, ValueError):
        return False
    return value >= limit > value - delta


def _signal(data, out, event):
    return _same((event.data or {}).get("signal"), data.get("name"))


def _moment(data, out, event):
    return _same((event.data or {}).get("moment"), data.get("moment"))


register(Kind("machine", "Машина", NOUN, "{host} {login}",
              (Field("host", "Машина", "machine", "", True), Field("login", "Учётка", "text", "любая; можно *")),
              (Sock("attempt", "◇ Попытка входа"), Sock("login", "Вошёл"), Sock("stopped", "Остановлена"), Sock("started", "Запущена")),
              events={"attempt": "machine.attempt", "login": "machine.login", "stopped": "machine.stopped", "started": "machine.started"}, match=_machine))
register(Kind("server", "Сервер сети", NOUN, "{address}/{path}",
              (Field("address", "Сервер", "text", "apollo.com", True), Field("path", "Путь", "text", "любой; можно *")),
              (Sock("attempt", "◇ Попытка запроса"), Sock("request", "Запросил страницу"), Sock("download", "Скачал файл"), Sock("denied", "Отказ")),
              events={"attempt": "net.attempt", "request": "net.request", "download": "net.download", "denied": "net.denied"}, match=_server))
register(Kind("command", "Команда", NOUN, "{command} {args}",
              (Field("command", "Команда", "text", "decrypt", True), Field("args", "Аргументы", "text", "любые; можно *"),
               Field("host", "Только на машине", "machine", "любой")),
              (Sock("run", "Выполнил"),), events={"run": "command.run"}, match=_command))
register(Kind("player_counter", "Счётчик игрока", NOUN, "count:{name} ≥ {threshold}",
              (Field("name", "Счётчик", "text", "hints", True), Field("threshold", "Порог", "number", "для «достиг»")),
              (Sock("changed", "Изменился"), Sock("reached", "Достиг порога")),
              events={"changed": "player.counter", "reached": "player.counter"}, match=_player_counter))
register(Kind("file", "Файл", NOUN, "{item} {path}",
              (Field("item", "Объект", "object", "любой"), Field("path", "Путь", "text", "любой; можно *"), Field("layer", "Слой", "text", "любой"),
               Field("override", "Вместо хуков слоя: хуки этого файла не срабатывают, работает граф", "bool")),
              (Sock("read", "Открыл"), Sock("deleted", "Удалил"), Sock("restored", "Вернул из корзины"), Sock("got", "Получил ключ"),
               Sock("joined", "Собрал ключ"), Sock("layer_removed", "Снял слой"), Sock("layer_attempt", "Ошибка на слое"),
               Sock("layer_failed", "Попытки кончились"), Sock(REF, "Файл")),
              events={"read": "file.read", "deleted": "file.deleted", "restored": "file.restored", "got": "key.got", "joined": "key.joined",
                      "layer_removed": "layer.removed", "layer_attempt": "layer.attempt", "layer_failed": "layer.failed"},
              match=_file, ref=("item", "item")))
register(Kind("character", "Персонаж", NOUN, "{character}",
              (Field("character", "Персонаж", "character", "", True), Field("text", "Текст", "text", "любой; можно *")),
              (Sock("mail", "Написал письмо"), Sock("air", "Позвал в эфире"), Sock("forum", "Написал на форуме"), Sock(REF, "Персонаж")),
              events={"mail": "character.wrote", "air": "character.wrote", "forum": "character.wrote"}, match=_character, ref=("character", "character")))
register(Kind("freq", "Частота", NOUN, "{freq}",
              (Field("freq", "Частота, МГц", "text", "7.205", True), Field("text", "Текст", "text", "любой; можно *")),
              (Sock("sent", "Передача"),), events={"sent": "air.sent"}, match=_freq))
register(Kind("section", "Раздел форума", NOUN, "раздел {section}", (Field("section", "Раздел", "section", "", True),),
              (Sock("topic", "Новая тема"), Sock("reply", "Ответ"), Sock(REF, "Раздел")),
              events={"topic": "forum.posted", "reply": "forum.posted"}, match=_section, ref=("section", "section")))
register(Kind("flag", "Метка игрока", NOUN, "tag:{name}", (Field("name", "Метка", "flag", "", True),),
              (Sock("set", "Поставили"), Sock("unset", "Сняли"), Sock(REF, "Метка")),
              events={"set": "flag.set", "unset": "flag.unset"}, match=_flag, ref=("flag", "name")))
register(Kind("world_flag", "Метка мира", NOUN, "world:{name}", (Field("name", "Метка мира", "world_flag", "", True),),
              (Sock("on", "Поставили"), Sock("off", "Сняли"), Sock(REF, "Метка")),
              events={"on": "world.flag", "off": "world.flag"}, match=_world_flag, ref=("world_flag", "name")))
register(Kind("counter", "Счётчик мира", NOUN, "world:{name} ≥ {threshold}",
              (Field("name", "Счётчик", "counter", "", True), Field("threshold", "Порог", "number", "для «достиг»")),
              (Sock("changed", "Изменился"), Sock("reached", "Достиг порога"), Sock(REF, "Счётчик")),
              events={"changed": "world.counter", "reached": "world.counter"}, match=_counter, ref=("counter", "name")))
register(Kind("moment", "Момент мира", NOUN, "{moment}", (Field("moment", "Момент", "moment", "", True),),
              (Sock("started", "Начался"), Sock("ended", "Кончился")),
              events={"started": "moment.started", "ended": "moment.ended"}, match=_moment))
register(Kind("time", "Время", NOUN, "{mode} {at}",
              (Field("mode", "Когда", "select", "", False, (("daily", "каждый день"), ("once", "один раз"))),
               Field("at", "Время (игровое, ЧЧ:ММ)", "clock", "21:00", True), Field("date", "Дата (для «один раз»)", "text", "2031-05-14"),
               Field("scope", "Для кого", "select", "", False, (("world", "мир"), ("each", "каждый игрок")))),
              (Sock("fire", "Наступило"),), events={"fire": TIME_EVENT}, start_only=True))
register(Kind("manual", "Запуск вручную", NOUN, "{label}", (Field("label", "Подпись кнопки", "text", "Запустить"),),
              (Sock("fire", "Запустили"),), events={"fire": MANUAL_EVENT}, start_only=True))
register(Kind("signal", "Сигнал", NOUN, "{name}", (Field("name", "Сигнал", "text", "bunker-open", True),),
              (Sock("got", "Пришёл"),), events={"got": SIGNAL_EVENT}, match=_signal))


OLD_NOUNS = ("machine", "server", "command", "player_counter", "file", "character", "freq", "section", "flag", "world_flag", "counter",
             "moment", "time")
for _name in OLD_NOUNS:
    KINDS[_name] = replace(KINDS[_name], hidden=True)


# ---------- когда: события по пространствам («Машина: Статус изменён») ----------

def _thing(value, wanted):
    return not wanted or _same(value, wanted)


def _match(**rules):
    """Сравнение события с фильтрами ноды: поле ноды -> (ключ события, как сравнивать). Пустой фильтр пропускает любое."""
    def match(data, out, event):
        d = {**(event.data or {}), "host": event.host, "login": event.login}
        for name, (key, how) in rules.items():
            wanted = data.get(name)
            if wanted in (None, ""):
                continue
            value = d.get(key, "")
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
        return True
    return match


def _when(name, label, fields, outs, events, match, data_outs, summary="", start_only=False):
    register(Kind(name, label, NOUN, summary, fields, outs, events=events, match=match, start_only=start_only))
    DATA_OUTS[name] = tuple(data_outs) + (Sock("player", "Игрок", "player", "@player"),)


THINGS_OF = ("character", "machine", "server", "object")
OWNER_WHEN = {"who": ("owner", ("player",)), "character": ("owner", ("character",)), "machine": ("owner", ("machine",)),
              "server": ("owner", ("server",)), "item": ("owner", ("object",)), "scope": ("owner", THINGS_OF),
              "for": (("owner", THINGS_OF), ("scope", ("player",)))}
_MACHINE = Field("machine", "Машина", "machine", "любая")
_OBJECT = Field("item", "Объект", "object", "любой")
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
_OBJECT_OUTS = (Sock("item", "Объект", "item", "item"), Sock("path", "Путь", "text", "path"), _HOST_OUT, _LOGIN_OUT)
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
      _OBJECT_OUTS + (Sock("via", "Откуда", "text", "via"),), "{item} {via}")


def _mail(data, out, event):
    return (event.data or {}).get("channel") == "mail" and _match(character=("character", "thing"), text=("text", "glob"))(data, out, event)


_when("on:player.mail", "Игрок: Отправил письмо", (Field("character", "Персонаж", "character", "любой"), Field("text", "Текст", "text", "любой; можно *")),
      (Sock("sent", "Отправил"),), {"sent": "character.wrote"}, _mail,
      (Sock("character", "Персонаж", "character", "character"), Sock("text", "Текст", "text", "text")), "{character}")
_when("on:player.air", "Игрок: Отправил в эфир", (Field("freq", "Частота, МГц", "text", "любая"), Field("text", "Текст", "text", "любой; можно *")),
      (Sock("sent", "Отправил"),), {"sent": "air.sent"}, _match(freq=("freq", "freq"), text=("text", "glob")),
      (Sock("freq", "Частота", "text", "freq"), Sock("text", "Текст", "text", "text"), Sock("callsign", "Позывной", "text", "callsign")), "{freq}")
_when("on:moment.status", "Момент: Статус изменён", (Field("moment", "Момент", "moment", "любой"),),
      (Sock("started", "Начался"), Sock("ended", "Кончился")), {"started": "moment.started", "ended": "moment.ended"},
      _match(moment=("moment", "thing")), (Sock("moment", "Момент", "moment", "moment"),), "{moment}")


def _value(data, event):
    """Тег или счётчик события тот же, что выбран в ноде: владелец, вещь, чьё (общее или для игрока «для игрока»), имя."""
    d = event.data or {}
    owner = data.get("owner") or "world"
    if d.get("owner") != owner or not _same(d.get("key"), data.get("name")):
        return False
    thing = data.get({"character": "character", "machine": "machine", "server": "server", "object": "item", "player": "who"}.get(owner, ""), "")
    if owner != "world" and thing not in (None, "") and not _same(d.get("thing"), thing):
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
register(Kind("once", "Однажды", FLOW, "", (), (Sock("pass", "Впервые"), Sock("again", "Уже было"))))
register(Kind("all", "Все из", FLOW, "{count}", (Field("count", "Сколько входов", "number", "2"),),
              (Sock("next", "Дальше"),), ins=(), many=(Many("in", "count", "i", "Вход {n}"),)))
register(Kind("race", "Первое из", FLOW, "{count}", (Field("count", "Сколько входов", "number", "2"),),
              ins=(), many=(Many("in", "count", "i", "Вход {n}"), Many("out", "count", "o", "Первым {n}"))))
register(Kind("end", "Конец", FLOW, "{outcome}",
              (Field("outcome", "Исход", "select", "", False, (("passed", "прошёл"), ("failed", "провалил"), ("aborted", "прервано"))),)))
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


def _actions():
    from engine.actions import HOST, REGISTRY
    from engine.context import SESSION

    for spec in REGISTRY.values():
        if spec.needs in (HOST, SESSION) or spec.run is None:      # эффекты браузера ждут доставки вне запроса (этап 3)
            continue
        register(Kind("do:" + spec.name, spec.label, ACTION, spec.summary, spec.fields, (Sock("next", "Сделано"), Sock("fail", "Не вышло")),
                      subgroup=spec.group, spec=spec, when=ACTION_WHEN.get(spec.name, {}), hidden=spec.name in LEGACY))


_actions()


# ---------- пояснения (подсказки на холсте, как в Blender) ----------

HELP = {
    "machine": "Машина и её учётки. Ловит вход игрока, остановку и запуск машины. ◇ Попытка входа — игрок стоит у двери, сценарий может ответить нодой «Ответить».",
    "server": "Внутриигровой сервер (nreq, nget). Ловит запросы страниц, скачивание файлов и отказ. ◇ Попытка запроса — ответить можно нодой «Ответить».",
    "command": "Команда терминала. Срабатывает, когда игрок её выполнил (с аргументами по образцу).",
    "player_counter": "Личный счётчик игрока (действие «Счётчик игрока»). Срабатывает, когда изменился или дошёл до порога.",
    "file": "Объект или файлы по пути. Ловит открытие, удаление, возврат, получение и сборку ключа, события слоёв. «Вместо хуков слоя» — хуки файла молчат, работает граф.",
    "character": "Персонаж. Срабатывает, когда игрок пишет ему: письмом, в эфире (полный позывной) или на форуме.",
    "freq": "Частота эфира. Срабатывает на передачу игрока на этой частоте (с текстом по образцу).",
    "section": "Раздел форума: новая тема или ответ игрока.",
    "flag": "Тег игрока (tag:имя): поставили или сняли.",
    "world_flag": "Метка мира (world:имя), одна на всех. Событие общее: будит ждущих у всех игроков.",
    "counter": "Счётчик мира. «Достиг порога» — в тот момент, когда значение перешло порог. Событие общее.",
    "moment": "Момент мира: начался или кончился. Событие общее.",
    "time": "Игровое время: каждый день или один раз в ЧЧ:ММ. Запускает прохождение мира или каждого игрока. Только старт.",
    "manual": "Кнопка автора: запустить прохождение для игрока или мира из панели ноды. Только старт.",
    "try:machine": "Вход на выбранную машину. Tab — граф входа этой машины: от «Попытки» до «Ответить», без ожиданий. "
                   "Выходы ноды — сокеты «Выхода» внутри графа: события и данные.",
    "attempt:machine": "Игрок пытается войти: подробности попытки. Дальше проверки и действия, конец — «Ответить».",
    "on:machine.status": "Машину остановили или запустили (для всех). Пустая машина — любая.",
    "on:terminal.command": "Игрок ввёл команду в терминале. Команда и аргументы понимают *.",
    "on:object.viewed": "Игрок открыл файл. Фильтры: объект, путь (*), машина; пусто — любой.",
    "on:object.deleted": "Игрок удалил файл (в корзину).", "on:object.restored": "Игрок вернул файл из корзины.",
    "on:object.changed": "Игрок сохранил правку текста файла.",
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
    "once": "Первый проход этого игрока — «Впервые», дальше — «Уже было».",
    "all": "Дальше, когда пришли все входы, в любом порядке.",
    "race": "Дальше по первому пришедшему входу; остальные ожидания, ведущие сюда, снимаются.",
    "end": "Прохождение закончено с исходом; все ждущие ветки снимаются.",
    "answer": "Ответ в графе попытки (у машины, сервера, слоя): впустить, отказать, заблокировать или как обычно — решают поля вещи.",
    "reroute": "Точка излома провода. Ничего не делает.",
    "group": "Группа нод (Ctrl+G). Tab — войти. Сокеты — её «Вход» и «Выход».",
    "group_in": "Вход группы или сценария: сокеты слева у ноды группы; сюда приходит «Запустить сценарий».",
    "group_out": "Выход группы или сценария: сокеты справа у ноды группы.",
    "scenario": "Другой сценарий целиком, как группа. Идёт в этом прохождении; его старты здесь не срабатывают.",
    "launch": "Запустить отдельное прохождение другого сценария для этого игрока, не дожидаясь его.",
    "send_signal": "Послать сигнал: будит ноды «Сигнал» с тем же именем у этого игрока или у всех.",
    "stage": "Отметка прохождения: счётчик «прошли» на холсте.",
    "note": "Заметка на холсте. Не исполняется.",
    "frame": "Рамка вокруг нод. Не исполняется.",
    "text": "Текст: значение для входов.", "number": "Число: значение для входов.", "boolean": "Да/нет: значение для входов.",
    "template": "Склеить текст: {имя} в шаблоне заменяется значением подстановки с этим именем. Заполнили подстановку — появляется следующая.",
    "compare": "Сравнить A и B: числа — как числа, остальное — как текст без учёта регистра. «По образцу» понимает *.",
    "logic": "И — все входы да; Или — хоть один да; Не — наоборот; Исключающее или — ровно один да. Подключили вход — появляется следующий.",
    "fact": "Условие на факты игрока прохождения: ключи, tag:, count:, world:. Верно или нет.",
    "math": "Посчитать A и B. «Случайное» — целое от A до B; округление, модуль и смена знака берут только A.",
    "read": "Прочитать сейчас: счётчик или метку мира, счётчик или метку игрока прохождения.",
    "ent:machine": "Машина: выбрать в ноде, получить проводом или найти по хосту/имени из текста. Свойства — как сейчас.",
    "ent:server": "Сетевой сервер (nreq, nget): по адресу.", "ent:object": "Объект библиотеки — содержимое, общее для всех; по слагу или названию.",
    "ent:character": "Персонаж: по коду или имени.", "ent:section": "Раздел форума: по номеру или названию.",
    "ent:moment": "Момент мира: по имени или названию; «Идёт» — сейчас ли он.",
    "ent:player": "Игрок: пусто — игрок прохождения, иначе по логину.",
    "switch": "Если «Если» — да, значение «Да», иначе «Нет». Так выход получает значение по условию.",
    "allowed": "поля вещи пустили (у «как обычно»)", "refused": "поля вещи отказали (у «как обычно»)",
    "ent:tag": "Тег владельца: мира, игрока, персонажа, машины, сервера или объекта; у вещи — общий или свой у игрока.",
    "ent:count": "Счётчик владельца, как у «Тега»; «Подпись» — подпись значения из описания счётчика («2» — «Архив»).",
    "do:tag": "Поставить или снять тег владельца (мир, игрок, вещь; у вещи — общий или для игрока).",
    "do:count": "Прибавить к счётчику владельца или задать его.",
    "files": "Где у игрока лежит объект: ищется по самому объекту на машинах, где у игрока есть учётка, поэтому перенос и переименование "
             "его не теряют. «Где» — машина:путь первой копии вне корзины.",
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
    "value": "значение", "player": "игрок прохождения (имя)", "path": "путь файла из события", "layer": "слой из события",
    "address": "адрес сервера", "command": "команда", "args": "аргументы команды", "text": "текст из события", "channel": "канал: mail, air, forum",
    "callsign": "позывной", "title": "заголовок или название", "lit": "стоит ли метка",
    "name": "имя или название", "host": "хост машины", "system": "код ОС машины", "up": "машина работает (не остановлена)",
    "code": "код персонажа", "active": "персонаж активен", "archived": "раздел в архиве", "running": "момент идёт сейчас",
    "format": "формат объекта", "has": "у игрока есть копия вне корзины", "where": "машина:путь первой копии", "count": "сколько копий вне корзины",
    "trash": "какая-то копия в корзине", "edited": "игрок поменял текст копии", "caption": "подпись значения",
    "stopped": "машину остановили", "viewed": "игрок открыл файл", "via": "откуда пришёл объект", "delta": "на сколько изменилось",
    "up": "значение дошло до порога снизу", "down": "значение ушло ниже порога", "ended": "момент кончился", "machine": "машина события",
    "item": "объект события", "moment": "момент события", "freq": "частота",
    "entered": "игрок вошёл (кто бы ни решал: граф или поля машины)", "denied": "в доступе отказано", "reason": "почему отказ: пароль, ключ, окно, граф…",
    "go": "попытка: дальше проверки, конец — «Ответить»",
}


# ---------- данные ----------

def _data(name, label, summary, fields, out_type, out_label="Значение", **extra):
    register(Kind(name, label, DATA, summary, fields, ins=(), **extra))
    DATA_OUTS[name] = (Sock("value", out_label, out_type),)


_P = ("@player",)
for _kind, _outs in {
    "machine": (Sock(REF, "Машина", "machine", "host", "host"), Sock("account", "Учётка", "text", "login", "login")),
    "server": (Sock("address", "Сервер", "text", "address", "address"), Sock("path", "Путь", "text", "path")),
    "command": (Sock("command", "Команда", "text", "command", "command"), Sock("args", "Аргументы", "text", "args")),
    "player_counter": (Sock("value", "Значение", "number", "value"),),
    "file": (Sock(REF, "Файл", "item", "item", "item"), Sock("path", "Путь", "text", "path", "path"), Sock("layer", "Слой", "text", "layer")),
    "character": (Sock(REF, "Персонаж", "character", "character", "character"), Sock("text", "Текст", "text", "text"),
                  Sock("channel", "Канал", "text", "channel")),
    "freq": (Sock("text", "Текст", "text", "text"), Sock("callsign", "Позывной", "text", "callsign")),
    "section": (Sock(REF, "Раздел", "section", "section", "section"), Sock("title", "Тема", "text", "title")),
    "flag": (Sock(REF, "Метка", "flag", "flag", "name"),),
    "world_flag": (Sock(REF, "Метка мира", "world_flag", "flag", "name"),),
    "counter": (Sock(REF, "Счётчик", "counter", "counter", "name"), Sock("value", "Значение", "number", "value")),
    "moment": (Sock(REF, "Момент", "moment", "moment", "moment"),),
    "signal": (),
    "time": (),
    "manual": (),
}.items():
    DATA_OUTS[_kind] = _outs + (Sock("player", "Игрок", "text", "@player"),)

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
_data("switch", "Выбрать значение", "",
      (Field("condition", "Если", "bool"), Field("yes", "Да", "text"), Field("no", "Нет", "text")), "text", "Значение")
KINDS["read"] = replace(KINDS["read"], hidden=True)                 # теперь «Тег» и «Счётчик»


# ---------- сущности: вещь мира и её свойства сейчас (graph/entities.py) ----------

def _entity(name, label, field, outs):
    register(Kind(name, label, ENTITY, "{%s}" % field.name, (field,), ins=()))
    DATA_OUTS[name] = outs


_entity("ent:machine", "Машина", Field("machine", "Машина", "machine"),
        (Sock("value", "Машина", "machine"), Sock("name", "Имя", "text"), Sock("host", "Хост", "text"), Sock("address", "Адрес", "text"),
         Sock("system", "ОС", "text"), Sock("up", "Работает", "bool")))
_entity("ent:server", "Сервер", Field("server", "Сервер", "server"),
        (Sock("value", "Сервер", "server"), Sock("address", "Адрес", "text"), Sock("title", "Название", "text")))
_entity("ent:object", "Объект", Field("item", "Объект", "object"),
        (Sock("value", "Объект", "item"), Sock("name", "Название", "text"), Sock("format", "Формат", "text")))
_entity("ent:character", "Персонаж", Field("character", "Персонаж", "character"),
        (Sock("value", "Персонаж", "character"), Sock("code", "Код", "text"), Sock("name", "Имя", "text"), Sock("callsign", "Позывной", "text"),
         Sock("active", "Активен", "bool")))
_entity("ent:section", "Раздел", Field("section", "Раздел", "section"),
        (Sock("value", "Раздел", "section"), Sock("title", "Название", "text"), Sock("archived", "В архиве", "bool")))
_entity("ent:moment", "Момент", Field("moment", "Момент", "moment"),
        (Sock("value", "Момент", "moment"), Sock("title", "Название", "text"), Sock("running", "Идёт", "bool")))
_entity("ent:player", "Игрок", Field("player", "Игрок", "player", "игрок прохождения"),
        (Sock("value", "Игрок", "player"), Sock("name", "Имя", "text"), Sock("callsign", "Позывной", "text")))
register(Kind("files", "Файлы игрока", ENTITY, "{item}", (
    Field("item", "Объект", "object", "", True), Field("player", "Игрок", "player", "игрок прохождения"), Field("machine", "Машина", "machine", "любая"),
), ins=()))
def _value_kind(name, label, outs):
    from engine.actions import OWNER_FIELDS

    register(Kind(name, label, ENTITY, "{owner} {name}", (*OWNER_FIELDS, Field("name", "Имя", "text", "", True)), ins=(),
                  subgroup="Теги и счётчики", when=OWNER_WHEN))
    DATA_OUTS[name] = outs


_value_kind("ent:tag", "Тег", (Sock("on", "Стоит", "bool"),))
_value_kind("ent:count", "Счётчик", (Sock("value", "Значение", "number"), Sock("caption", "Подпись", "text")))
DATA_OUTS["files"] = (Sock("has", "Есть", "bool"), Sock("where", "Где", "text"), Sock("count", "Копий", "number"),
                      Sock("trash", "В корзине", "bool"), Sock("edited", "Изменён игроком", "bool"))


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


def sock_type(kind, data, side, name, iface=None):
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
            "hidden": k.hidden, "owned": k.owned,
        } for k in sorted(KINDS.values(), key=lambda k: list(GROUPS).index(k.group))],
    }
