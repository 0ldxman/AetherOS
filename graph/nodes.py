"""Виды нод сценария. Нода в документе: {"id", "type", "x", "y", "data": {поле: значение}}; провод: {"id", "from", "out",
"to", "in"}. Провод потока идёт из выхода в вход "in" (или i1, i2… у «Все из» и «Первое из»); провод-ссылка идёт из выхода
"ref" существительного во вход "f:<поле>" действия: поле берёт значение вещи.

Группы: noun — существительные (вещь мира и её события; нода без входящего провода — старт, со входящим — ожидание), flow — ход,
action — действия движка (engine/actions.py), service — служебные.
"""
import fnmatch
from dataclasses import dataclass, field

from engine.actions import Field

NOUN, FLOW, ACTION, STRUCT, SERVICE = "noun", "flow", "action", "struct", "service"
GROUPS = {NOUN: "Существительные", FLOW: "Ход", ACTION: "Действия", STRUCT: "Сценарии и группы", SERVICE: "Служебные"}
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


@dataclass(frozen=True)
class Many:
    """Повторяемые сокеты: число из поля (или длина списка в нём). Имена prefix1, prefix2…; подпись — шаблон с {n} или {label}.
    Пустой prefix: имя берётся из элемента списка (поле name) — так у «Входа» и «Выхода» группы имена не сдвигаются при удалении."""
    side: str
    field: str
    prefix: str
    label: str


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


KINDS = {}


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
register(Kind("flag", "Метка игрока", NOUN, "flag:{name}", (Field("name", "Метка", "flag", "", True),),
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
register(Kind("manual", "Вручную", NOUN, "{label}", (Field("label", "Подпись кнопки", "text", "Запустить"),),
              (Sock("fire", "Запустили"),), events={"fire": MANUAL_EVENT}, start_only=True))
register(Kind("signal", "Сигнал", NOUN, "{name}", (Field("name", "Сигнал", "text", "bunker-open", True),),
              (Sock("got", "Пришёл"),), events={"got": SIGNAL_EVENT}, match=_signal))


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
              (Sock("next", "Дальше"),)))
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


def _actions():
    from engine.actions import HOST, REGISTRY
    from engine.context import SESSION

    for spec in REGISTRY.values():
        if spec.needs in (HOST, SESSION) or spec.run is None:      # эффекты браузера ждут доставки вне запроса (этап 3)
            continue
        register(Kind("do:" + spec.name, spec.label, ACTION, spec.summary, spec.fields, (Sock("next", "Дальше"), Sock("fail", "Не вышло")),
                      subgroup=spec.group, spec=spec))


_actions()


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


def sockets(kind, data, side, iface=None):
    """Имена сокетов ноды с её данными: side "in" или "out". У группы и сценария — по их интерфейсу iface
    {"inputs": [имя], "outputs": [имя]} (его даёт тот, кто знает определение группы или другой граф)."""
    if kind.name in BOXES:
        return list((iface or {}).get("inputs" if side == "in" else "outputs") or [])
    names = list(kind.ins if side == "in" else [sock.name for sock in kind.outs])
    for many in kind.many:
        if many.side == side:
            if not many.prefix:
                names += [name for name, _ in named(data, many.field)]
            else:
                names += [f"{many.prefix}{n}" for n in range(1, len(_count(data, many.field)) + 1)]
    if side == "out":
        names += [sock.name for sock in kind.tail]
        if kind.group == NOUN and not kind.start_only:
            names.append(TIMEOUT)                    # есть только у ждущей ноды (со входом)
    return names


def catalog():
    """Виды нод для Студии."""
    def fields(items):
        return [{"name": f.name, "label": f.label, "kind": f.kind, "placeholder": f.placeholder, "required": f.required,
                 "options": [{"value": v, "label": label} for v, label in f.options]} for f in items]

    return {
        "groups": [{"name": name, "label": label} for name, label in GROUPS.items()],
        "start_fields": fields(START_FIELDS),
        "wait_fields": fields(WAIT_FIELDS),
        "ref_kinds": REF_KINDS,
        "kinds": [{
            "name": k.name, "label": k.label, "group": k.group, "subgroup": k.subgroup, "summary": k.summary, "fields": fields(k.fields),
            "ins": list(k.ins), "outs": [{"name": s.name, "label": s.label} for s in k.outs],
            "many": [{"side": m.side, "field": m.field, "prefix": m.prefix, "label": m.label} for m in k.many],
            "tail": [{"name": s.name, "label": s.label} for s in k.tail],
            "ref": k.ref[0] if k.ref else "", "start_only": k.start_only,
        } for k in KINDS.values()],
    }
