"""Исполнитель сценариев.

Событие (engine.events.emit) будит ждущие ветки и запускает старты: существительное без входящего провода. Прохождение идёт
по проводам потока, пока не упрётся в ожидание (событие, время, условие) или в конец. Время и условия двигает tick() из
middleware мира. Прохождение одного игрока в одном сценарии — Run; где стоят его ветки — Wait.

Действия выполняются словарём движка от имени игрока хода; учётка — та, на которой случилось событие (host, login).
Ни одна ошибка сценария не роняет игру: причина пишется в журнал мира.
"""
import contextvars
import logging
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from graph import nodes as N
from graph.models import Graph, Hit, Mark, Run, Start, Wait

log = logging.getLogger("graph")

LIST_LIMIT = 200                             # «Для каждого» проходит не больше стольких элементов
DEPTH = 8          # сценарий → действие → событие → сценарий…
STEPS = 300        # нод за один проход: защита от цикла без ожидания
TICK = 15
_depth = contextvars.ContextVar("graph_depth", default=0)
_answer = contextvars.ContextVar("graph_answer", default=None)       # попытка ждёт «Ответить»: {"answer": None | {...}}
_lock = threading.Lock()
_last = {"at": 0.0}


# ---------- документ ----------

class Doc:
    """Граф в удобном виде: ноды по id, провода потока из (нода, выход), ссылки во входы-поля."""

    def __init__(self, doc):
        doc = doc or {}
        self.deps = list(doc.get("_deps") or [])
        self.nodes = {str(node.get("id")): node for node in doc.get("nodes") or [] if isinstance(node, dict) and node.get("id")}
        self.flow, self.refs, self.fed, self.into = {}, {}, set(), {}
        for wire in doc.get("wires") or []:
            if not isinstance(wire, dict):
                continue
            src, out, dst, inp = str(wire.get("from")), str(wire.get("out")), str(wire.get("to")), str(wire.get("in"))
            if src not in self.nodes or dst not in self.nodes:
                continue
            self.into[(dst, inp)] = (src, out)
            if inp.startswith("f:"):
                self.refs[(dst, inp[2:])] = (src, out)
            else:
                self.flow.setdefault((src, out), []).append((dst, inp))
                self.fed.add(dst)

    def next(self, node_id, out):
        return list(self.flow.get((node_id, out), []))

    def kind(self, node_id):
        node = self.nodes.get(node_id)
        return N.KINDS.get(node.get("type")) if node else None

    def data(self, node_id):
        return (self.nodes.get(node_id) or {}).get("data") or {}

    def wired(self, node_id):
        """Выходы ноды, от которых идут провода потока."""
        return [out for (src, out) in self.flow if src == node_id]

    def is_start(self, node_id):
        kind = self.kind(node_id)
        return kind is not None and kind.group == N.NOUN and node_id not in self.fed and not self.nodes[node_id].get("_inline")

    def reaching(self, target):
        """Ноды, из которых по проводам потока можно дойти до target."""
        back = {}
        for (src, _), targets in self.flow.items():
            for dst, _ in targets:
                back.setdefault(dst, set()).add(src)
        seen, queue = set(), deque([target])
        while queue:
            for src in back.get(queue.popleft(), ()):
                if src not in seen:
                    seen.add(src)
                    queue.append(src)
        return seen


DEPTH_BOXES = 6


def _first(part, kind):
    for node in (part or {}).get("nodes") or []:
        if isinstance(node, dict) and node.get("type") == kind:
            return str(node.get("id"))
    return None


def _load(slug):
    return Graph.objects.filter(slug=str(slug or "")).only("slug", "doc", "updated_at").first()


def iface(part):
    """Интерфейс группы или сценария: имена сокетов его «Входа» и «Выхода»."""
    def node(kind):
        return next((n for n in (part or {}).get("nodes") or [] if isinstance(n, dict) and n.get("type") == kind), None)

    def names(kind):
        found = node(kind)
        return [name for name, _ in N.named(found.get("data"))] if found else []

    return {"inputs": names("group_in"), "outputs": names("group_out"),
            "in_types": N.socket_types((node("group_in") or {}).get("data")), "out_types": N.socket_types((node("group_out") or {}).get("data"))}


def _expand(part, groups, prefix, inline, depth, seen, nodes, wires, deps):
    """Развернуть уровень графа: ноды групп и вложенных сценариев заменяются их содержимым с префиксом «нода/»; провода в
    обёртку идут в её «Вход», из обёртки — из её «Выхода» (они пропускают поток по имени сокета)."""
    boxes = {}
    for node in (part or {}).get("nodes") or []:
        if not isinstance(node, dict) or not node.get("id"):
            continue
        nid, kind, data = str(node["id"]), node.get("type"), node.get("data") or {}
        full = prefix + nid
        if kind == "group":
            inner = groups.get(str(data.get("group") or ""))
            if inner is not None and depth < DEPTH_BOXES:
                _expand(inner, groups, full + "/", inline, depth + 1, seen, nodes, wires, deps)
                boxes[nid] = (full, inner)
            continue
        if kind == "scenario":
            other = _load(data.get("graph"))
            if other is not None and other.slug not in seen and depth < DEPTH_BOXES:
                deps.append((other.slug, other.updated_at.isoformat()))
                inner = other.doc or {}
                _expand(inner, inner.get("groups") or {}, full + "/", True, depth + 1, seen | {other.slug}, nodes, wires, deps)
                boxes[nid] = (full, inner)
            continue
        nodes.append({**node, "id": full, "_inline": inline or bool(node.get("_inline"))})
    plain = {str(node.get("id")) for node in (part or {}).get("nodes") or [] if isinstance(node, dict)} - set(boxes)
    for wire in (part or {}).get("wires") or []:
        if not isinstance(wire, dict):
            continue
        src, out, dst, inp = (str(wire.get(name) or "") for name in ("from", "out", "to", "in"))
        if src in boxes:
            inner_out = _first(boxes[src][1], "group_out")
            if inner_out is None:
                continue
            src = boxes[src][0] + "/" + inner_out
        elif src in plain:
            src = prefix + src
        else:
            continue
        if dst in boxes:
            if inp.startswith("f:"):
                continue
            inner_in = _first(boxes[dst][1], "group_in")
            if inner_in is None:
                continue
            dst = boxes[dst][0] + "/" + inner_in
        elif dst in plain:
            dst = prefix + dst
        else:
            continue
        wires.append({"from": src, "out": out, "to": dst, "in": inp})


def flatten(raw, slug=""):
    """Граф с развёрнутыми группами и вложенными сценариями (для исполнения и проверки циклов)."""
    nodes, wires, deps = [], [], []
    _expand(raw or {}, (raw or {}).get("groups") or {}, "", False, 0, frozenset({slug}) if slug else frozenset(), nodes, wires, deps)
    return {"nodes": nodes, "wires": wires, "_deps": deps}


_docs = {}


def doc_of(graph):
    """Развёрнутый граф из кэша; кэш сбрасывается, когда меняется сам граф или любой вложенный в него сценарий."""
    key = (graph.pk, graph.updated_at)
    found = _docs.get(graph.pk)
    if found is not None and found[0] == key and found[1].deps:
        slugs = [slug for slug, _ in found[1].deps]
        now = {slug: at.isoformat() for slug, at in Graph.objects.filter(slug__in=slugs).values_list("slug", "updated_at")}
        if any(now.get(slug) != at for slug, at in found[1].deps):
            found = None
    if found is None or found[0] != key:
        found = (key, Doc(flatten(graph.doc, graph.slug)))
        _docs[graph.pk] = found
    return found[1]


def rebuild_starts(graph):
    """Выписать старты: существительные без входа и события их подключённых выходов."""
    doc = Doc(flatten(graph.doc, graph.slug))
    rows = []
    for node_id in doc.nodes:
        if not doc.is_start(node_id):
            continue
        kind = doc.kind(node_id)
        for out in doc.wired(node_id):
            event = N.event_of(kind, out)
            if event:
                rows.append(Start(graph=graph, node=node_id, out=out, event=event))
    with transaction.atomic():
        Start.objects.filter(graph=graph).delete()
        Start.objects.bulk_create(rows)
    return rows


# ---------- помощники ----------

def _log(graph, text, user=None):
    from world import state

    try:
        state._log("graph", graph.slug, text[:400], f"сценарий {graph.slug}", user)
    except Exception:                               # noqa: BLE001
        log.exception("graph log failed")


def _ctx_of(event):
    return {"host": event.host, "login": event.login, "event": event.name, "data": event.data or {}}


def _box(run):
    host, login = (run.ctx or {}).get("host"), (run.ctx or {}).get("login")
    if run.user is None or not host or not login:
        return None
    from machines.models import MachineProfile
    from mail.boxes import Box

    profile = MachineProfile.objects.select_related("machine").filter(machine__hostname=host, login=login).first()
    return Box.of_profile(profile, run.user) if profile is not None else None


def _facts(run):
    if run.user is None:
        return frozenset()
    from engine.chains import player_facts

    return player_facts(run.user)


_parsed = {}


def parse_condition(text):
    """Условие из текста (как в цепочках): структура для secure.access или ошибка ValueError."""
    from documents.markup.expr import SpoilerSyntaxError, parse_expr

    text = (text or "").strip()
    if not text:
        raise ValueError("пустое условие")
    if text not in _parsed:
        try:
            _parsed[text] = parse_expr(text)
        except SpoilerSyntaxError as error:
            raise ValueError(str(error)) from None
    return _parsed[text]


def _truth(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() not in ("", "0", "false", "no", "нет")


def _holds(text, run, known=None):
    """Условие: да/нет с провода или текст условия на факты игрока."""
    from secure.access import satisfied

    if isinstance(text, (bool, int, float)):
        return _truth(text)
    try:
        condition = parse_condition(text)
    except ValueError as error:
        _log(run.graph, f"условие «{text}»: {error}", run.user)
        return False
    return bool(satisfied(condition, _facts(run) if known is None else known))


def _fill(value, run):
    """Подставить подробности события в текст: {host}, {login}, {path}, {slug}… Неизвестное остаётся как есть."""
    if not isinstance(value, str) or "{" not in value:
        return value
    ctx = run.ctx or {}
    known = {"host": ctx.get("host", ""), "login": ctx.get("login", "")}
    known.update({key: item for key, item in (ctx.get("data") or {}).items() if isinstance(item, (str, int, float))})
    return re.sub(r"\{(\w+)\}", lambda m: str(known[m.group(1)]) if m.group(1) in known else m.group(0), value)


def _clock(text):
    found = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(text or ""))
    if not found or int(found.group(1)) > 23 or int(found.group(2)) > 59:
        raise ValueError(f"время «{text}»: нужно ЧЧ:ММ")
    return int(found.group(1)), int(found.group(2))


def after(minutes, real=False):
    """Реальный момент, когда пройдёт minutes минут: игровых (если время идёт) или реальных."""
    from machines.world import chrono

    delta = timedelta(minutes=max(0.0, float(minutes or 0)))
    if real or chrono.rate_now() <= 0:
        return timezone.now() + delta
    found = chrono.to_real(chrono.game_now() + delta)
    return found if found is not None else timezone.now() + delta


def until_clock(text, real=False):
    """Ближайший реальный момент, когда часы (игровые или реальные) покажут ЧЧ:ММ."""
    from machines.world import chrono

    hour, minute = _clock(text)
    if real:
        now = timezone.localtime()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target if target > now else target + timedelta(days=1)
    game = chrono.game_now()
    target = game.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= game:
        target += timedelta(days=1)
    return chrono.to_real(target)


# ---------- выполнение нод ----------

def _hit(run, node_id):
    Hit.objects.create(graph=run.graph, node=node_id, user=run.user, run=run)


def _mark(run, node_id, user=None):
    """Счётчик ноды под блокировкой (вызывать внутри atomic)."""
    found, _ = Mark.objects.select_for_update().get_or_create(graph=run.graph, node=node_id, user=user)
    return found


def _count(data, name, default=2):
    try:
        return max(1, min(int(data.get(name) or default), 12))
    except (TypeError, ValueError):
        return default


# ---------- данные: значения по проводам ----------

def capture(run, node_id, event=None, ctx=None):
    """Запомнить подробности события существительного: из них берутся его выходы данных (путь, учётка, значение…)."""
    if event is not None:
        found, user = {**(event.data or {}), "host": event.host, "login": event.login}, event.user
    else:
        found, user = {**((ctx or {}).get("data") or {}), "host": (ctx or {}).get("host", ""), "login": (ctx or {}).get("login", "")}, run.user
    found.update({key: value for key, value in N.moved_paths(found).items() if key not in found})
    if found["host"] and user is not None:                                     # где случилось: размещение игрока (и где было до изменения)
        for key, path in (("placement", "after"), ("from_placement", "before")):
            if found.get(path) and key not in found:
                found[key] = f"{user.get_username()}@{found['host']}:{found[path]}"
    run.state = {**(run.state or {}), "vals": {**((run.state or {}).get("vals") or {}), node_id: found}}


def _number(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _plain(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def value_of(run, doc, node_id, out, depth=0):
    """Значение выхода данных: подробность события существительного, результат ноды данных или проход через вход/выход группы."""
    if depth > 30:
        return None
    kind = doc.kind(node_id)
    if kind is None:
        return None
    data = doc.data(node_id)
    if kind.name in ("group_in", "group_out"):
        src = doc.into.get((node_id, out))
        return value_of(run, doc, src[0], src[1], depth + 1) if src else None
    if kind.name == "foreach":                       # элемент и номер текущего прохода ветки «Каждый»
        return (((run.state or {}).get("vals") or {}).get(node_id) or {}).get(out)
    if kind.group == N.NOUN:
        if kind.owned:                               # данные «Выхода» графа попытки приехали с событием
            return (((run.state or {}).get("vals") or {}).get(node_id) or {}).get("vals", {}).get(out)
        sock = N.data_out(kind, out)
        if sock is None:
            return None
        if sock.key == "@player":
            return run.user.get_username() if run.user is not None else ""
        found = ((run.state or {}).get("vals") or {}).get(node_id) or {}
        value = found.get(sock.key)
        if value in (None, "") and sock.fallback:
            value = data.get(sock.fallback)
        return value
    get = lambda name: input_of(run, doc, node_id, name, depth + 1)       # noqa: E731
    if kind.group == N.ENTITY:
        from graph import entities

        if kind.name == "find":
            return entities.find(run, kind, {f.name: get(f.name) for f in kind.fields})
        if kind.name == "ent:placement":
            return entities.placement(run, kind, {f.name: get(f.name) for f in kind.fields}, out)
        if kind.name in ("ent:tag", "ent:count"):
            return entities.value(run, kind, {f.name: get(f.name) for f in kind.fields}, out)
        if kind.name == "ent:layer":
            return entities.layer(run, kind, {f.name: get(f.name) for f in kind.fields}, out)
        return entities.read(run, kind, get(kind.fields[0].name), out)
    if kind.group != N.DATA:
        return None
    name = kind.name
    if name == "text":
        return str(get("value") or "")
    if name == "number":
        return _plain(_number(get("value")) or 0)
    if name == "boolean":
        return _truth(get("value"))
    if name == "template":
        values = {}
        for row in N.rows(kind, data):
            if str(row.get("name") or "").strip():
                value = get(row["id"])
                values[str(row["name"]).strip()] = "" if value is None else str(_plain(value))
        return re.sub(r"\{([^{}]+)\}", lambda m: values.get(m.group(1).strip(), m.group(0)), str(get("template") or ""))
    if name == "compare":
        a, b, op = get("a"), get("b"), data.get("op") or "eq"
        na, nb = _number(a), _number(b)
        if op in ("gt", "ge", "lt", "le"):
            if na is None or nb is None:
                return False
            return {"gt": na > nb, "ge": na >= nb, "lt": na < nb, "le": na <= nb}[op]
        sa, sb = str(a if a is not None else ""), str(b if b is not None else "")
        if op == "contains":
            return sb.casefold() in sa.casefold()
        if op == "like":
            import fnmatch

            return fnmatch.fnmatchcase(sa.casefold(), sb.casefold())
        same = (na == nb) if na is not None and nb is not None else sa.strip().casefold() == sb.strip().casefold()
        return same if op == "eq" else not same
    if name == "logic":
        ids = [row["id"] for row in N.rows(kind, data)]
        ids += sorted({inp for (dst, inp) in doc.refs if dst == node_id and N.is_row(kind, inp) and inp not in ids})
        values = [_truth(get(row_id)) for row_id in ids]
        op = data.get("op") or "and"
        if op == "not":
            return not (values[0] if values else False)
        if op == "or":
            return any(values)
        if op == "xor":
            return sum(values) == 1
        return bool(values) and all(values)
    if name == "fact":
        return _holds(get("expr"), run)
    if name == "list.make":
        ids = [row["id"] for row in N.rows(kind, data)]
        ids += sorted({inp for (dst, inp) in doc.refs if dst == node_id and N.is_row(kind, inp) and inp not in ids})
        return [value for value in (get(row_id) for row_id in ids) if value not in (None, "")]
    if name == "list.count":
        return len(_as_list(get("list")))
    if name == "list.item":
        items = _as_list(get("list"))
        mode = data.get("mode") or "first"
        index = 0 if mode == "first" else len(items) - 1 if mode == "last" else int(_number(get("number")) or 1) - 1
        found = 0 <= index < len(items)
        return found if out == "found" else (items[index] if found else None)
    if name == "list.has":
        wanted = str(_plain(get("value")) if get("value") is not None else "").strip().casefold()
        return any(str(_plain(item)).strip().casefold() == wanted for item in _as_list(get("list")))
    if name == "switch":
        value = get("yes") if _truth(get("condition")) else get("no")
        return "" if value is None else str(_plain(value))
    if name == "math":
        a, b, op = _number(get("a")) or 0, _number(get("b")) or 0, data.get("op") or "add"
        if op == "random":
            import random

            low, high = sorted((int(a), int(b)))
            return random.randint(low, high)
        import math

        try:
            result = {"add": lambda: a + b, "sub": lambda: a - b, "mul": lambda: a * b, "div": lambda: a / b if b else 0,
                      "mod": lambda: a % b if b else 0, "pow": lambda: a ** b, "min": lambda: min(a, b), "max": lambda: max(a, b),
                      "round": lambda: round(a), "floor": lambda: math.floor(a), "ceil": lambda: math.ceil(a), "abs": lambda: abs(a),
                      "neg": lambda: -a}.get(op, lambda: 0)()
        except (OverflowError, ValueError, ZeroDivisionError):
            result = 0
        if isinstance(result, complex):
            result = 0
        return _plain(float(result))
    if name == "read":
        return _read(run, data.get("what") or "world_counter", str(get("name") or ""), out)
    return None


def _read(run, what, name, out):
    from engine import values

    player = run.user.pk if run is not None and run.user is not None else None
    if what == "world_counter":
        value = values.get(values.COUNT, values.WORLD, 0, name)
    elif what == "player_counter":
        value = values.get(values.COUNT, values.PLAYER, player, name)
    elif what == "world_flag":
        value = values.get(values.TAG, values.WORLD, 0, name)
    else:
        value = values.get(values.TAG, values.PLAYER, player, name)
    return bool(value) if out == "lit" else value


def _as_list(value):
    if value in (None, ""):
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _shape(kind, data, name, value):
    """Значение под тип входа: одно значение во вход-список — списком из одного, список во вход-текст — через запятую."""
    wanted = N.sock_type(kind, data, "in", f"f:{name}")
    if N.is_list(wanted):
        return _as_list(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(_plain(item)) for item in value) if wanted == "text" else (value[0] if value else None)
    return value


def input_of(run, doc, node_id, name, depth=0):
    """Значение входа-поля: с провода, а без провода — то, что вписано в ноду."""
    src = doc.refs.get((node_id, name))
    if src is not None:
        kind = doc.kind(node_id)
        value = value_of(run, doc, src[0], src[1], depth)
        return _shape(kind, doc.data(node_id), name, value) if kind is not None else value
    data = doc.data(node_id)
    kind = doc.kind(node_id)
    if kind is not None and N.is_row(kind, name):
        return next((row.get("value") for row in N.rows(kind, data) if row.get("id") == name), None)
    return data.get(name)


def resolved(run, doc, node_id):
    """Данные ноды с подставленными значениями проводов."""
    data = dict(doc.data(node_id))
    kind = doc.kind(node_id)
    for (dst, name), (src, out) in doc.refs.items():
        if dst == node_id:
            value = value_of(run, doc, src, out)
            data[name] = _shape(kind, data, name, value) if kind is not None else value
    return data


def _noun_wait(run, doc, node_id, kind):
    data = resolved(run, doc, node_id)
    outs = [out for out in doc.wired(node_id) if N.event_of(kind, out)]
    own = bool(data.get("own"))
    if data.get("past") and (run.user is not None or not own):
        from engine.models import Event

        past = Event.objects.filter(name__in={N.event_of(kind, out) for out in outs})
        for event in (past.filter(user=run.user) if own else past)[:300]:
            for out in outs:
                if N.event_of(kind, out) == event.name and kind.match(data, out, event):
                    run.ctx = {**(run.ctx or {}), **_ctx_of(event), "host": event.host or run.ctx.get("host"), "login": event.login or run.ctx.get("login")}
                    _take(run, event)
                    capture(run, node_id, event)
                    return [out]
    fed = {name: data[name] for (dst, name) in doc.refs if dst == node_id}       # фильтры с проводов: значения на момент ожидания
    for out in outs:
        Wait.objects.create(run=run, user=run.user, node=node_id, out=out, kind=Wait.Kind.EVENT, event=N.event_of(kind, out), anyone=not own,
                            data=fed)
    if data.get("timeout") not in (None, "", 0, "0") and N.TIMEOUT in doc.wired(node_id):
        Wait.objects.create(run=run, user=run.user, node=node_id, out=N.TIMEOUT, kind=Wait.Kind.TIME, until=after(data.get("timeout")))
    return []


def _wait(run, doc, node_id):
    data = resolved(run, doc, node_id)
    mode, real = data.get("mode") or "delay", bool(data.get("real"))
    if mode == "condition":
        if _holds(data.get("condition"), run):
            return ["next"]
        Wait.objects.create(run=run, user=run.user, node=node_id, out="next", kind=Wait.Kind.CONDITION)
        if data.get("timeout") not in (None, "", 0, "0"):
            Wait.objects.create(run=run, user=run.user, node=node_id, out=N.TIMEOUT, kind=Wait.Kind.TIME, until=after(data.get("timeout"), real))
        return []
    try:
        until = until_clock(data.get("at"), real) if mode == "until" else after(data.get("minutes") or 0, real)
    except ValueError as error:
        _log(run.graph, f"ждать: {error}", run.user)
        return []
    if until is None:
        _log(run.graph, "ждать: игровое время стоит, срок не наступит", run.user)
    Wait.objects.create(run=run, user=run.user, node=node_id, out="next", kind=Wait.Kind.TIME, until=until)
    return []


def _action(run, doc, node_id, kind):
    from engine import actions as engine
    from engine.context import Ctx

    spec, action = N.action_of(kind, resolved(run, doc, node_id))
    action = {key: _fill(_plain(value) if isinstance(value, float) else value, run) if key != "do" else value for key, value in action.items()}
    ctx = Ctx(source=f"сценарий {run.graph.slug}", user=run.user, box=_box(run), depth=_depth.get())
    have = ctx.provides()
    if spec.needs not in have:
        need = {"user": "игрока", "account": "учётки игрока (событие было не на машине)"}.get(spec.needs, spec.needs)
        _log(run.graph, f"«{spec.label}»: нет {need}", run.user)
        return ["fail"]
    problems = engine.check([action], provides=have)
    if problems:
        _log(run.graph, f"«{spec.label}»: {'; '.join(problems)}", run.user)
        return ["fail"]
    try:
        spec.run(action, ctx)
    except (engine.ActionError, ValueError) as error:
        _log(run.graph, f"«{spec.label}»: {error}", run.user)
        return ["fail"]
    return ["next"]


def _execute(run, doc, node_id, sock):
    """Выполнить ноду; вернуть выходы, по которым идти дальше."""
    import random

    kind, data = doc.kind(node_id), resolved(run, doc, node_id)
    name = kind.name
    if kind.group == N.NOUN:
        return [] if kind.start_only else _noun_wait(run, doc, node_id, kind)
    if kind.group == N.ACTION:
        return _action(run, doc, node_id, kind)
    if name in ("reroute", "stage"):
        return ["next"]
    if name in ("group_in", "group_out"):
        if name == "group_out" and getattr(run.graph, "owner", "") and "/" not in node_id:
            from engine.events import emit                  # свой выход графа попытки: событие для ноды попытки в сценариях

            ctx = run.ctx or {}
            types = N.socket_types(doc.data(node_id))
            vals = {name: _plain(value_of(run, doc, node_id, name)) for name, kind_of in types.items() if kind_of != N.EVENT}
            emit(N.OWNED_OUT, run.user, machine=ctx.get("host") or None, login=ctx.get("login", ""), owner=run.graph.owner, socket=sock,
                 vals={k: v for k, v in vals.items() if isinstance(v, (str, int, float, bool)) or v is None})
        return [sock]                               # пропускает поток по имени сокета
    if name == "send_signal":
        from engine.events import emit

        everyone = data.get("to") == "all"
        emit(N.SIGNAL_EVENT, None if everyone else run.user, source=f"сценарий {run.graph.slug}", signal=str(data.get("name") or ""), all=everyone)
        return ["next"]
    if name == "launch":
        return [_launch(run, data)]
    if name == "answer":
        holder = _answer.get()
        if holder is None:
            _log(run.graph, "«Ответить» без попытки: ответ некому", run.user)
        elif holder.get("answer") is None:
            minutes = max(1, min(int(data.get("minutes") or 10), 30 * 24 * 60)) if str(data.get("minutes") or "").lstrip("-").isdigit() else 10
            holder["answer"] = {"mode": data.get("mode") or "allow", "text": _fill(str(data.get("text") or ""), run), "minutes": minutes}
            if holder["answer"]["mode"] == "default":
                _outcome_waits(run, doc, node_id)
        return ["next"]
    if name == "wait":
        return _wait(run, doc, node_id)
    if name == "check":
        return ["yes" if _holds(data.get("condition"), run) else "no"]
    if name == "choose":
        known = _facts(run)
        for number, row in enumerate(data.get("rows") or [], 1):
            if isinstance(row, dict) and _holds(row.get("condition"), run, known):
                return [f"r{number}"]
        return ["else"]
    if name == "random":
        weights = []
        for value in data.get("branches") or [1, 1]:
            try:
                weights.append(max(0.0, float(value)))
            except (TypeError, ValueError):
                weights.append(0.0)
        if not any(weights):
            return []
        return [f"b{random.choices(range(1, len(weights) + 1), weights=weights)[0]}"]
    if name == "turns":
        with transaction.atomic():
            mark = _mark(run, node_id)
            number = mark.value % _count(data, "count") + 1
            mark.value += 1
            mark.save(update_fields=["value"])
        return [f"b{number}"]
    if name == "first":
        with transaction.atomic():
            mark = _mark(run, node_id)
            if mark.value >= _count(data, "count", 1):
                return ["late"]
            mark.value += 1
            mark.save(update_fields=["value"])
        return ["pass"]
    if name == "once":
        with transaction.atomic():
            mark = _mark(run, node_id, run.user if data.get("per") == "player" else None)
            if mark.value:
                return ["again"]
            mark.value = 1
            mark.save(update_fields=["value"])
        return ["pass"]
    if name == "all":
        joins = dict((run.state or {}).get("joins") or {})
        got = set(joins.get(node_id) or []) | {sock}
        if len(got) >= _count(data, "count"):
            joins.pop(node_id, None)
            run.state = {**(run.state or {}), "joins": joins}
            return ["next"]
        joins[node_id] = sorted(got)
        run.state = {**(run.state or {}), "joins": joins}
        return []
    if name == "race":
        done = list((run.state or {}).get("races") or [])
        if node_id in done or not sock.startswith("i"):
            return []
        run.state = {**(run.state or {}), "races": done + [node_id]}
        Wait.objects.filter(run=run, node__in=doc.reaching(node_id)).delete()
        return [f"o{sock[1:]}"]
    if name == "end":
        _finish(run, data.get("outcome") or "passed")
        return []
    return []


def _launch(run, data):
    """Запустить другой сценарий с его «Входа» для того же игрока, не дожидаясь его."""
    target = Graph.objects.filter(slug=str(data.get("graph") or ""), active=True).first()
    if target is None:
        _log(run.graph, f"запустить: нет включённого сценария «{data.get('graph')}»", run.user)
        return "fail"
    doc = doc_of(target)
    entry = next((nid for nid, node in doc.nodes.items() if node.get("type") == "group_in" and "/" not in nid), None)
    names = [name for name, _ in N.named(doc.data(entry))] if entry else []
    socket = str(data.get("socket") or "").strip() or (names[0] if names else "")
    if entry is None or socket not in names:
        _log(run.graph, f"запустить: у сценария «{target.slug}» нет входа «{socket or '?'}»", run.user)
        return "fail"
    start(target, entry, socket, run.user, dict(run.ctx or {}), repeat="always")
    return "next"


def _finish(run, outcome=""):
    run.status, run.outcome, run.ended_at = Run.Status.DONE, outcome, timezone.now()
    Wait.objects.filter(run=run).delete()


def advance(run, items):
    """Пройти от входов items [(нода, вход)] до ожиданий и концов."""
    doc = doc_of(run.graph)
    _drain(run, doc, deque(items), [0])
    if run.status == Run.Status.RUNNING and not Wait.objects.filter(run=run).exists():
        _finish(run, run.outcome or "")
    run.save(update_fields=["status", "outcome", "ended_at", "ctx", "state"])
    return run


def _drain(run, doc, queue, steps):
    """Очередь нод до конца. «Для каждого» проходит ветку «Каждый» целиком по разу на элемент, потом идёт в «Готово»."""
    while queue and run.status == Run.Status.RUNNING:
        node_id, sock = queue.popleft()
        kind = doc.kind(node_id)
        if kind is None or kind.name in ("note", "frame") or kind.group in (N.DATA, N.ENTITY):
            continue
        if doc.nodes[node_id].get("mute"):                 # выключенная нода пропускает поток насквозь (как M в Blender)
            if "next" in N.sockets(kind, doc.data(node_id), "out"):
                queue.extend(doc.next(node_id, "next"))
            continue
        steps[0] += 1
        if steps[0] > STEPS:
            _log(run.graph, f"больше {STEPS} нод за раз: цикл без ожидания? Прохождение остановлено", run.user)
            _finish(run, "aborted")
            break
        _hit(run, node_id)
        if kind.name == "foreach":
            for index, item in enumerate(_as_list(input_of(run, doc, node_id, "list"))[:LIST_LIMIT], 1):
                vals = {**((run.state or {}).get("vals") or {}), node_id: {"item": item, "index": index}}
                run.state = {**(run.state or {}), "vals": vals}
                _drain(run, doc, deque(doc.next(node_id, "each")), steps)
            queue.extend(doc.next(node_id, "done"))
            continue
        try:
            outs = _execute(run, doc, node_id, sock)
        except Exception as error:                   # noqa: BLE001 — сломанная нода не роняет игру
            log.exception("graph node %s failed", node_id)
            _log(run.graph, f"нода {kind.label}: {error}", run.user)
            outs = []
        for out in outs:
            queue.extend(doc.next(node_id, out))


# ---------- старт и пробуждение ----------

DEFAULT_REPEAT = {"manual": "always", "on:time": "always", "on:schedule": "always",
                  "on:moment.status": "always", "on:machine.status": "always"}


def start(graph, node_id, out, user=None, ctx=None, repeat=None):
    """Запустить прохождение со старта node_id по выходу out. Возвращает Run или None (по правилу повтора не нужно)."""
    doc = doc_of(graph)
    kind = doc.kind(node_id)
    if kind is None:
        return None
    repeat = repeat or doc.data(node_id).get("repeat") or DEFAULT_REPEAT.get(kind.name, "once")
    with transaction.atomic():
        Graph.objects.select_for_update().filter(pk=graph.pk).first()      # два события сразу: правило повтора видит одно
        runs = Run.objects.filter(graph=graph, node=node_id)              # прохождение одно на всех: «один раз» — за игру
        if repeat == "once" and runs.exists():
            return None
        if repeat == "end" and runs.filter(status=Run.Status.RUNNING).exists():
            return None
        run = Run.objects.create(graph=graph, user=user, node=node_id, ctx=ctx or {})
    run.graph = graph
    capture(run, node_id, ctx=ctx or {})
    _hit(run, node_id)
    return advance(run, doc.next(node_id, out))


def _take(run, event):
    """Событие другого игрока продвинуло ход: дальше ход идёт с ним (его машина, учётка, письма — ему). True, если игрок сменился."""
    if event.user is None or run.user_id == event.user.pk:
        return False
    run.user = event.user
    Run.objects.filter(pk=run.pk).update(user=event.user)
    Wait.objects.filter(run=run).update(user=event.user)
    return True


def resume(wait, event=None):
    """Ожидание сработало: снять все ожидания ноды и идти дальше по его выходу."""
    with transaction.atomic():
        run = Run.objects.select_for_update().select_related("graph").filter(pk=wait.run_id).first()
        if run is None or run.status != Run.Status.RUNNING:
            return None
        deleted, _ = Wait.objects.filter(run=run, node=wait.node).delete()
        if not deleted:
            return None                              # уже сработало в другом запросе
        if event is not None:
            ctx = run.ctx or {}
            took = _take(run, event)
            run.ctx = {**ctx, "event": event.name, "data": {**(ctx.get("data") or {}), **(event.data or {})},
                       "host": event.host if took else ctx.get("host") or event.host, "login": event.login if took else ctx.get("login") or event.login}
            capture(run, wait.node, event)
    return advance(run, doc_of(run.graph).next(wait.node, wait.out))


def follow(event):
    """Файл переехал (перенос, удаление в корзину, возврат): ждущие его ноды и запомненные размещения идут за ним (файл тот же)."""
    paths = N.moved_paths(event.data)
    if event.user is None or not event.host or not paths or paths["before"] == paths["after"]:
        return
    name = event.user.get_username()
    old, new = f"{name}@{event.host}:{paths['before']}", f"{name}@{event.host}:{paths['after']}"
    for wait in Wait.objects.filter(run__status=Run.Status.RUNNING, data__placement=old):
        wait.data = {**wait.data, "placement": new}
        wait.save(update_fields=["data"])
    for run in Run.objects.filter(status=Run.Status.RUNNING, graph__active=True):
        vals = (run.state or {}).get("vals") or {}
        moved = {node: {**found, "placement": new, "path": paths["after"], "after": paths["after"]} for node, found in vals.items()
                 if isinstance(found, dict) and found.get("placement") == old}
        if moved:
            run.state = {**run.state, "vals": {**vals, **moved}}
            run.save(update_fields=["state"])


def dispatch(event):
    """Событие из engine.events.emit: разбудить ожидания и запустить старты. Возвращает число затронутых прохождений."""
    depth = _depth.get()
    if depth >= DEPTH:
        return 0
    token = _depth.set(depth + 1)
    touched = 0
    try:
        waits = Wait.objects.filter(kind=Wait.Kind.EVENT, event=event.name, run__status=Run.Status.RUNNING, run__graph__active=True)
        if event.user is not None and event.name not in N.GLOBAL_EVENTS and not (event.data or {}).get("shared"):
            waits = waits.filter(Q(user=event.user) | Q(anyone=True))
        # событие без игрока (сигнал всем, метка мира, момент, машина) будит ждущих у всех
        for wait in list(waits.select_related("run__graph")):
            kind = doc_of(wait.run.graph).kind(wait.node)
            if kind is not None and kind.match is not None and kind.match({**doc_of(wait.run.graph).data(wait.node), **(wait.data or {})}, wait.out, event):
                touched += bool(resume(wait, event))
        if event.user is not None:
            for wait in list(Wait.objects.filter(kind=Wait.Kind.CONDITION, user=event.user, run__status=Run.Status.RUNNING,
                                                 run__graph__active=True).select_related("run__graph")):
                if _holds(resolved(wait.run, doc_of(wait.run.graph), wait.node).get("condition"), wait.run):
                    touched += bool(resume(wait))
        for row in list(Start.objects.filter(event=event.name, graph__active=True).select_related("graph")):
            doc = doc_of(row.graph)
            kind = doc.kind(row.node)
            data = doc.data(row.node)
            if kind is not None and kind.owned:
                from graph import owned

                data = {**data, kind.fields[0].name: owned.thing_of(doc, row.node)}
            if kind is not None and kind.match is not None and kind.match(data, row.out, event):
                touched += bool(start(row.graph, row.node, row.out, event.user, _ctx_of(event)))
        if event.name in ("file.moved", "file.deleted", "file.restored"):
            follow(event)
    finally:
        _depth.reset(token)
    return touched


OUTCOMES = {"machine": ("machine.login", "machine.denied"), "net.request": ("net.request", "net.denied"),       # «как обычно»: чем кончилось,
            "net.download": ("net.download", "net.denied"), "layer": ("layer.removed", "layer.attempt")}         # когда решила сама вещь


def _outcome_waits(run, doc, node_id):
    """«Ответить: как обычно»: ждать, что решат поля вещи, и пойти по «Пустили» или «Отказали» (прежняя попытка игрока снимается)."""
    events = OUTCOMES.get((run.graph.owner or "").split(":")[0])
    wired = doc.wired(node_id)
    if not events or not ({"allowed", "refused"} & set(wired)):
        return
    Wait.objects.filter(run__graph=run.graph, user=run.user, node=node_id, kind=Wait.Kind.EVENT).exclude(run=run).delete()
    ctx = run.ctx or {}
    for out, event in zip(("allowed", "refused"), events):
        if out in wired:
            Wait.objects.create(run=run, user=run.user, node=node_id, out=out, kind=Wait.Kind.EVENT, event=event,
                                data={"_host": ctx.get("host", ""), "_login": ctx.get("login", "")})


def decide(graph, user, *, host="", login="", **data):
    """Граф попытки у вещи решает сразу: от стартовой «Попытки» до «Ответить». Ответ {"mode", "text", "minutes"} или None."""
    from engine.events import _clean

    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    doc = doc_of(graph)
    node_id = next((nid for nid, node in doc.nodes.items() if str(node.get("type") or "").startswith("attempt:") and "/" not in nid), None)
    if node_id is None:
        return None
    holder = {"answer": None}
    token = _answer.set(holder)
    try:
        start(graph, node_id, "go", user, {"host": host, "login": login, "event": "@attempt", "data": _clean(data)}, repeat="always")
    finally:
        _answer.reset(token)
    found = holder["answer"]
    return None if found is None or found["mode"] == "default" else found


def start_manual(graph, node_id, user=None):
    """Кнопка автора «Вручную»: запустить для игрока или для мира."""
    kind = doc_of(graph).kind(node_id)
    if kind is None or kind.name != "manual":
        raise ValueError("это не нода «Вручную»")
    return start(graph, node_id, "fire", user, {"event": N.MANUAL_EVENT}, repeat="always")


# ---------- время ----------

DAYS = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6, "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _days(text):
    found = set()
    for word in re.findall(r"[a-zа-яё]+", str(text or "").lower()):
        key = word[:3] if word[:3] in DAYS else word[:2]
        if key in DAYS:
            found.add(DAYS[key])
    if not found:
        raise ValueError("нет дней недели")
    return found


def _time_target(data, game, kind_name="time"):
    """Последний срок не позже game: у «В момент» — дата и время, у «По расписанию» — по режиму."""
    if kind_name == "on:time":
        data = {**data, "mode": "once"}
    elif kind_name == "on:schedule":
        mode = data.get("mode") or "daily"
        if mode == "every":
            step = max(1, int(_number(data.get("minutes")) or 60))
            midnight = game.replace(hour=0, minute=0, second=0, microsecond=0)
            passed = int((game - midnight).total_seconds() // 60)
            return midnight + timedelta(minutes=passed - passed % step)
        hour, minute = _clock(data.get("at"))
        target = game.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target > game:
            target -= timedelta(days=1)
        if mode == "weekly":
            days = _days(data.get("days"))
            while target.weekday() not in days:
                target -= timedelta(days=1)
        return target
    hour, minute = _clock(data.get("at"))
    if (data.get("mode") or "daily") == "once":
        day = datetime.strptime(str(data.get("date") or "").strip(), "%Y-%m-%d")
        return day.replace(hour=hour, minute=minute, tzinfo=dt_timezone.utc)
    target = game.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target <= game else target - timedelta(days=1)


def _time_starts():
    from engine.chains import _players
    from machines.world import chrono

    game = chrono.game_now()
    fired = 0
    for row in list(Start.objects.filter(event=N.TIME_EVENT, graph__active=True).select_related("graph")):
        doc = doc_of(row.graph)
        data, kind = doc.data(row.node), doc.kind(row.node)
        try:
            target = _time_target(data, game, kind.name if kind else "time")
        except ValueError:
            continue
        stamp = int(target.timestamp())
        with transaction.atomic():
            mark, created = Mark.objects.select_for_update().get_or_create(graph=row.graph, node=row.node, user=None)
            if created:                              # только что включили: прошедшее не догоняем
                mark.value = stamp if game >= target else 0
                mark.save(update_fields=["value"])
                continue
            if game < target or mark.value >= stamp:
                continue
            mark.value = stamp
            mark.save(update_fields=["value"])
        users = list(_players()) if data.get("scope") == "each" else [None]
        for user in users:
            fired += bool(start(row.graph, row.node, "fire", user, {"event": N.TIME_EVENT}))
    return fired


def tick(force=False):
    """Сработавшие сроки, условия и старты по времени. Не чаще раза в TICK секунд на процесс."""
    if not force:
        with _lock:
            if time.monotonic() - _last["at"] < TICK:
                return 0
            _last["at"] = time.monotonic()
    done = 0
    for wait in list(Wait.objects.filter(until__lte=timezone.now(), run__status=Run.Status.RUNNING, run__graph__active=True).select_related("run__graph")):
        done += bool(resume(wait))
    for wait in list(Wait.objects.filter(kind=Wait.Kind.CONDITION, run__status=Run.Status.RUNNING, run__graph__active=True).select_related("run__graph")):
        if _holds(resolved(wait.run, doc_of(wait.run.graph), wait.node).get("condition"), wait.run):
            done += bool(resume(wait))
    done += _time_starts()
    return done
