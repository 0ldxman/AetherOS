"""Исполнитель сценариев.

Событие (engine.events.emit) будит ждущие ветки и запускает старты: существительное без входящего провода. Прохождение идёт
по проводам потока, пока не упрётся в ожидание (событие, время, условие) или в конец. Время и условия двигает tick() из
middleware мира. Прохождение одного игрока в одном сценарии — Run; где стоят его ветки — Wait.

Действия выполняются словарём движка от имени инициатора; учётка — та, на которой случилось событие (host, login).
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

LIST_LIMIT = 200                             # «Ожидание веток» проходит не больше стольких элементов
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
            elif self._value_into(src, out, dst, inp):           # во вход потока пришло значение («Когда»: условие)
                self.refs[(dst, inp)] = (src, out)
            else:
                self.flow.setdefault((src, out), []).append((dst, inp))
                self.fed.add(dst)

    def _value_into(self, src, out, dst, inp):
        kind, src_kind = self.kind(dst), self.kind(src)
        return (kind is not None and src_kind is not None and inp in kind.in_types
                and N.sock_type(src_kind, self.data(src), "out", out) != N.EVENT)

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
        return kind is not None and kind.group in N.NOUNS and node_id not in self.fed and not self.nodes[node_id].get("_inline")

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
        if kind in ("each", "watch", "branching"):
            inner = groups.get(str(data.get("group") or ""))
            nodes.append({**node, "id": full, "_inline": inline or bool(node.get("_inline"))})
            if inner is not None and depth < DEPTH_BOXES:
                _expand(inner, groups, full + "/", True, depth + 1, seen, nodes, wires, deps)
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
    for node_id in doc.nodes:                       # действие с условием во «Когда»: делать, пока верно
        if doc.kind(node_id) is not None and doc.kind(node_id).name in N.UNDO and (node_id, "in") in doc.refs:
            rows.append(Start(graph=graph, node=node_id, out=N.BIND, event=N.WHILE_EVENT))
    from graph import offers

    with transaction.atomic():
        Start.objects.filter(graph=graph).delete()
        Start.objects.bulk_create(rows)
        offers.declare(graph, doc)
    open_watches(graph)
    return rows


# ---------- помощники ----------

def _character_act(run, kind, data):
    """«Персонаж: Написать» и «Персонаж: Ответить» (characters/outbox.py): реплика с отметкой сценария."""
    from characters import outbox
    from characters.models import Character, Inbound

    text = _fill(str(data.get("text") or ""), run)
    slug = run.graph.slug
    try:
        if kind.name == "act:character.reply":
            raw = str(data.get("message") or "").strip()
            inbound = Inbound.objects.select_related("character").filter(pk=int(raw)).first() if raw.isdigit() else None
            if inbound is None:
                raise outbox.OutboxError("нет сообщения: подайте провод «Сообщение»")
            outbox.answer(inbound, None, text, subject=_fill(str(data.get("subject") or ""), run), graph=slug)
            return ["next"]
        character = Character.objects.filter(code__iexact=str(data.get("character") or "").strip()).first()
        if character is None:
            raise outbox.OutboxError("не выбран персонаж")
        channel = data.get("channel") or "mail"
        if channel == "forum":
            from forum.models import Section, Topic

            raw = str(data.get("section") or "").strip()
            section = Section.objects.filter(pk=int(raw), archived=False).first() if raw.isdigit() else None
            if section is None:
                raise outbox.OutboxError("нет раздела форума")
            title = _fill(str(data.get("title") or ""), run).strip()
            if (data.get("topic") or "new") == "append":
                topic = Topic.objects.filter(section=section, title__iexact=title, hidden_at__isnull=True).order_by("-pk").first()
                if topic is None:
                    raise outbox.OutboxError(f"нет темы «{title}»")
                outbox.to_topic(character, topic, text, graph=slug)
            else:
                outbox.say(character, None, Inbound.Channel.FORUM, text, section=section, title=title, graph=slug)
            return ["next"]
        if channel == "air":
            outbox.say(character, None, Inbound.Channel.AIR, text, freq=_fill(str(data.get("freq") or ""), run).strip(),
                       user=run.user, graph=slug)
            return ["next"]
        from filesystem.models import Item

        item = Item.objects.filter(slug=str(data.get("letter") or "").strip()).first() if data.get("letter") else None
        if data.get("letter") and item is None:
            raise outbox.OutboxError(f"нет письма «{data.get('letter')}»")
        subject = _fill(str(data.get("subject") or ""), run)
        common = dict(subject=subject, item=item, graph=slug)
        to = data.get("to") or "list"
        if to == "all":
            outbox.say(character, None, Inbound.Channel.MAIL, text, audience="all", **common)
            return ["next"]
        if to == "list":
            targets = outbox.recipients(_as_list(data.get("targets")))
        elif to == "event" and (run.ctx or {}).get("host") and (run.ctx or {}).get("login"):
            from machines.models import MachineProfile

            targets = list(MachineProfile.objects.filter(machine__hostname=run.ctx["host"], login=run.ctx["login"]).select_related("machine")[:1])
        else:
            from machines.current import home_account

            targets = [home_account(run.user)] if run.user is not None else []
        if not targets:
            raise outbox.OutboxError("некому отправить")
        for profile in targets:
            outbox.say(character, None, Inbound.Channel.MAIL, text, account=profile, user=run.user, **common)
    except outbox.OutboxError as error:
        _log(run.graph, f"«{kind.label}»: {error}", run.user)
        return ["fail"]
    return ["next"]


def _thing_find(run, kind, data, get, out):
    """«Найти по условию»: найдено (список), первое, количество."""
    from engine import search

    among = get("among")
    limit = get("limit")
    try:
        order = data.get("order") or ("count" if data.get("sort") else "name")             # sort — прежнее поле порядка по счётчику
        direction = {"name": data.get("name_dir") or "asc", "count": data.get("count_dir") or "desc"}.get(order, data.get("time_dir") or "asc")
        found = search.find(get("expr"), data.get("what") or "account", run.user, _facts(run),
                            among=_as_list(among) if among not in (None, "") else None, order=order, by=get("by") or data.get("sort") or "",
                            descending=direction == "desc",
                            limit=int(float(limit)) if str(limit or "").strip().replace(".", "", 1).isdigit() else None)
    except search.SearchError as error:
        _log(run.graph, f"«{kind.label}»: {error}", run.user)
        found = []
    if out == "count":
        return len(found)
    if out == "first":
        return found[0] if found else ""
    return found


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


def _fill(value, run, keep=()):
    """Подставить подробности события в текст: {host}, {login}, {path}, {slug}… Неизвестное остаётся как есть,
    пустое из keep — тоже (его подставит действие: учётка игрока на машине)."""
    if not isinstance(value, str) or "{" not in value:
        return value
    ctx = run.ctx or {}
    known = {"host": ctx.get("host", ""), "login": ctx.get("login", ""), "player": run.user.get_username() if getattr(run, "user", None) is not None else ""}
    known.update({key: item for key, item in (ctx.get("data") or {}).items() if isinstance(item, (str, int, float))})
    known = {key: item for key, item in known.items() if key not in keep or item not in (None, "")}
    return re.sub(r"\{(\w+)\}", lambda m: str(known[m.group(1)]) if m.group(1) in known else m.group(0), value)


def _clock(text):
    from graph import times

    found = times.clock(text)
    if found is None:
        raise ValueError(f"время «{text}»: нужно ЧЧ:ММ или дата ГГГГ-ММ-ДД ЧЧ:ММ")
    return found


def after(minutes, real=False):
    """Реальный момент, когда пройдёт minutes минут: игровых (если время идёт) или реальных."""
    from machines.world import chrono

    delta = timedelta(minutes=max(0.0, float(minutes or 0)))
    if real or chrono.rate_now() <= 0:
        return timezone.now() + delta
    found = chrono.to_real(chrono.game_now() + delta)
    return found if found is not None else timezone.now() + delta


def until_clock(text, real=False):
    """Ближайший реальный момент, когда часы (игровые или реальные) покажут ЧЧ:ММ; дата «ГГГГ-ММ-ДД ЧЧ:ММ» — этот момент."""
    from graph import times
    from machines.world import chrono

    moment = times.parse(text, words=False) if times.clock(text) is None else None
    if moment is not None:
        return moment if real else chrono.to_real(moment)
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


def _int(data, name, default=0):
    """Целое поле ноды без потолка (в отличие от _count): пусто и «0 — без предела» дают default."""
    try:
        return max(0, int(float(data.get(name) or default)))
    except (TypeError, ValueError):
        return default


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
        if found.get("login") and "account" not in found:                                  # учётка события: «логин@хост»
            found["account"] = f"{found['login']}@{found['host']}"
        if found.get("id") and found.get("placement") and "layer_key" not in found:          # событие слоя: какой слой
            found["layer_key"] = f"{found['placement']}#{found['id']}"
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
    if kind.name == "branch_head":                    # кому сейчас принадлежит ветка
        return run.crew.name if run.crew_id else run.owner.get_username() if run.owner_id else ""
    if kind.name in ("branch_in", "each", "watch", "wait_cond", "join", "crew"):  # элемент и номер ветки; у «Ожидание веток» — кто успел и кто первый
        return (((run.state or {}).get("vals") or {}).get(node_id) or {}).get(out)
    if kind.group in N.NOUNS:
        if kind.owned:                               # данные «Выхода» графа попытки приехали с событием
            return (((run.state or {}).get("vals") or {}).get(node_id) or {}).get("vals", {}).get(out)
        if kind.name == N.USED_OFFER and out.startswith("fork:"):        # слово развилки текста варианта
            return ((((run.state or {}).get("vals") or {}).get(node_id) or {}).get("forks") or {}).get(out[5:], "")
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
    if kind.name in N.PLACEMENT_ACTS or kind.name in N.MACHINE_ACTS:    # что сделало действие: запомнено при выполнении
        return (((run.state or {}).get("vals") or {}).get(node_id) or {}).get(out)
    get = lambda name: input_of(run, doc, node_id, name, depth + 1)       # noqa: E731
    if kind.name == "act:mail" and out == "item":                       # письмо, которое отправляет нода
        return get("item")
    if kind.group in (N.ENTITY, N.ATTR):
        from graph import entities

        if kind.name == "session.find":
            from graph import sessions

            return sessions.find(run, data.get("mode") or "current", get("player"), get("machine"), _truth(get("active")), get("account"))
        if kind.name == "find":
            return entities.find(run, kind, {f.name: get(f.name) for f in kind.fields})
        if kind.name == "thing.find":
            return _thing_find(run, kind, data, get, out)
        if kind.name == "ent:placement":
            return entities.placement(run, kind, {f.name: get(f.name) for f in kind.fields}, out)
        if kind.name in ("ent:tag", "ent:count"):
            found = {**doc.data(node_id), **{f.name: get(f.name) for f in kind.fields}}      # и прежний выбор владельца (owner, machine…)
            return entities.value(run, kind, _inferred(doc, node_id, kind, found), out)
        if kind.name == "ent:account":
            return entities.account(run, kind, {f.name: get(f.name) for f in kind.fields}, out)
        if kind.name == "ent:mount":
            return entities.mount(run, kind, {f.name: get(f.name) for f in kind.fields}, out)
        if kind.name == "ent:layer":
            return entities.layer(run, kind, {f.name: get(f.name) for f in kind.fields}, out)
        if kind.name == "ent:offer":
            from graph import offers

            return offers.entity_value(run, node_id, out)
        return entities.read(run, kind, get(kind.fields[0].name), out)
    if kind.group != N.DATA:
        return None
    name = kind.name
    if name == "text":
        values = {}
        for row in N.rows(kind, data):
            if str(row.get("name") or "").strip():
                value = get(row["id"])
                values[str(row["name"]).strip()] = "" if value is None else str(_plain(value))
        body = str(get("value") or "")
        return re.sub(r"\{([^{}]+)\}", lambda m: values.get(m.group(1).strip(), m.group(0)), body) if values else body
    if name == "number":
        return _plain(_number(get("value")) or 0)
    if name == "boolean":
        return _truth(get("value"))
    if name in ("time.get", "time.calc", "time.zone", "time.parts"):
        from graph import times

        if name == "time.get":
            return times.outputs(times.moment(data.get("what") or "datetime", data.get("source") or "now", get("value"))).get(out, "")
        if name == "time.calc":
            if out == "diff":
                return times.diff(get("a") or "сейчас", get("b"), data.get("unit") or "seconds")
            return times.shift(get("a") or "сейчас", *(_number(get(part)) or 0 for part in ("days", "hours", "minutes", "seconds")))
        if name == "time.zone":
            return times.in_zone(get("value") or "сейчас", get("zone"))
        from graph import entities

        machine = entities._machine(entities._key(get("machine")))
        return times.parts(get("value") or "сейчас", machine).get(out, 0)
    if name == "compare":
        a, b, op = get("a"), get("b"), data.get("op") or "eq"
        na, nb = _number(a), _number(b)
        if na is None or nb is None:                                     # даты — как даты
            from graph import times

            da, db = times.parse(a, words=False), times.parse(b, words=False)
            if da is not None and db is not None:
                na, nb = da.timestamp(), db.timestamp()
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
        found = [value for value in (get(row_id) for row_id in ids) if value not in (None, "")]
        return len(found) if out == "count" else found
    if name == "list.content":
        items = _as_list(get("list"))
        if out == "count":
            return len(items)
        if out == "has":
            wanted = {str(_plain(w)).strip().casefold() for w in _as_list(get("value"))}            # одно или список: хоть одно
            return any(str(_plain(item)).strip().casefold() in wanted for item in items)
        pick = data.get("pick") or "first"
        index = 0 if pick == "first" else len(items) - 1 if pick == "last" else int(_number(get("number")) or 1) - 1
        found = 0 <= index < len(items)
        return found if out == "found" else (items[index] if found else None)
    if name == "list.action":
        return _list_action(list(_as_list(get("list"))), data.get("mode") or "add", data, get).get(out)
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


def _list_action(items, mode, data, get):
    """«Список: Действие»: {"list": новый список, "item": достали, "found": нашёлся ли}. Номера с 1."""
    number = lambda name: int(_number(get(name)) or 1) - 1      # noqa: E731
    if mode in ("add", "remove"):
        where = data.get("where") or "end"
        if mode == "add":
            value = get("value")
            if value not in (None, ""):
                items.insert(len(items) if where == "end" else 0 if where == "start" else max(0, min(len(items), number("at"))), value)
            return {"list": items}
        index = len(items) - 1 if where == "end" else 0 if where == "start" else number("at")
        if 0 <= index < len(items):
            items.pop(index)
        return {"list": items}
    if (data.get("by") or "index") == "value":
        wanted = str(_plain(get("item"))).strip().casefold()
        index = next((i for i, one in enumerate(items) if str(_plain(one)).strip().casefold() == wanted), -1)
    else:
        index = number("number")
    found = 0 <= index < len(items)
    return {"list": items, "item": items.pop(index) if found else None, "found": found}


def _as_list(value):
    if value in (None, ""):
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _shape(kind, data, name, value):
    """Значение под тип входа: одно значение во вход-список — списком из одного, список во вход-текст — через запятую."""
    wanted = N.sock_type(kind, data, "in", f"f:{name}")
    if N.is_list(wanted):
        return _as_list(value)
    if N.is_many(wanted):                           # «одно или список»: как пришло
        return list(value) if isinstance(value, tuple) else value
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
    return _inferred(doc, node_id, kind, data)


def _inferred(doc, node_id, kind, data):
    """Тип провода задаёт поля ноды (Kind.infers): машина в «Владелец» — владелец «машина»."""
    if kind is None or not kind.infers:
        return data
    types = {}
    for name in kind.infers:
        src = doc.refs.get((node_id, name))
        if src is not None and doc.kind(src[0]) is not None:
            types[name] = N.sock_type(doc.kind(src[0]), doc.data(src[0]), "out", src[1])
    return N.inferred(kind, data, types)


def _noun_wait(run, doc, node_id, kind):
    data = resolved(run, doc, node_id)
    outs = [out for out in doc.wired(node_id) if N.event_of(kind, out)]
    item = (run.state or {}).get("item") or {}
    own = data.get("own") in (True, "player", "true") or (data.get("own") == "item" and bool(item.get("user")))
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
    for name, (mode, by) in kind.infers.items():                                 # и то, что задал тип провода (владелец и его вещь)
        if name in fed:
            fed.update({key: data.get(key) for key in (mode, *(f for _, f in by.values()))})
    if data.get("own") == "item" and item.get("account") and not item.get("user"):
        fed["@account"] = item["account"]                                         # элемент-учётка: только события на ней
    for out in outs:
        Wait.objects.create(run=run, user=run.user, node=node_id, out=out, kind=Wait.Kind.EVENT, event=N.event_of(kind, out),
                            anyone=not own or bool(run.owner_id or run.crew_id or (run.state or {}).get("vacancy")), data=fed)
    if data.get("timeout") not in (None, "", 0, "0") and N.TIMEOUT in doc.wired(node_id):
        Wait.objects.create(run=run, user=run.user, node=node_id, out=N.TIMEOUT, kind=Wait.Kind.TIME, until=after(data.get("timeout")))
    return []


def _join(run, doc, node_id, data, sock):
    """«Ожидание входов»: Все — когда пришли все подключённые входы; Любой — первый (остальные ожидания снимаются); По количеству — N входов."""
    if not (sock.startswith("i") and sock[1:].isdigit()):
        return []
    wired = {inp for (dst, inp) in doc.into if dst == node_id and inp.startswith("i") and inp[1:].isdigit()}
    total = max(1, len(wired))
    mode = data.get("mode") or "all"
    need = 1 if mode == "any" else min(_count(data, "need", 2), total) if mode == "count" else total
    state = run.state or {}
    done = list(state.get("races") or [])
    if node_id in done:
        return []                                        # «Любой» и «По количеству» срабатывают один раз за поток
    joins = dict(state.get("joins") or {})
    got = set(joins.get(node_id) or []) | {sock}
    if len(got) < need:
        run.state = {**state, "joins": {**joins, node_id: sorted(got)}}
        return []
    joins.pop(node_id, None)
    vals = {**(state.get("vals") or {}), node_id: {"input": int(sock[1:])}}
    run.state = {**state, "joins": joins, "vals": vals, **({"races": done + [node_id]} if mode != "all" else {})}
    if mode != "all":
        Wait.objects.filter(run=run, node__in=doc.reaching(node_id)).delete()
    return ["next"]


def _met(run, node_id):
    """Условие выполнено: запомнить игровое время («Когда»)."""
    from graph import times

    vals = {**((run.state or {}).get("vals") or {}), node_id: {"when": times.text(times.now())}}
    run.state = {**(run.state or {}), "vals": vals}


def _wait_cond(run, doc, node_id):
    """«Ждать условие»: верно сейчас — дальше сразу, иначе стоим и пересчитываем на событиях инициатора и по таймеру."""
    if _holds(resolved(run, doc, node_id).get("condition"), run):
        _met(run, node_id)
        return ["next"]
    Wait.objects.create(run=run, user=run.user, node=node_id, out="next", kind=Wait.Kind.CONDITION)
    return []


def _wait(run, doc, node_id):
    data = resolved(run, doc, node_id)
    mode, real = data.get("mode") or "delay", bool(data.get("real"))
    minutes = sum((_number(data.get(name)) or 0) * factor for name, factor in (("seconds", 1 / 60), ("minutes", 1), ("hours", 60), ("days", 1440)))
    try:
        until = until_clock(data.get("at"), real) if mode == "until" else after(minutes, real)
    except ValueError as error:
        _log(run.graph, f"ждать: {error}", run.user)
        return []
    if until is None:
        _log(run.graph, "ждать: игровое время стоит, срок не наступит", run.user)
    Wait.objects.create(run=run, user=run.user, node=node_id, out="next", kind=Wait.Kind.TIME, until=until)
    return []


def _action(run, doc, node_id, kind, override=None):
    import itertools

    data = {**resolved(run, doc, node_id), **(override or {})}
    lists = [f.name for f in kind.fields if N.is_many(f.kind) and isinstance(data.get(f.name), (list, tuple))]
    if lists:                                       # «одно или список»: действие с каждым (с каждым сочетанием)
        outs = set()
        for combo in list(itertools.product(*(list(data[name]) for name in lists)))[:LIST_LIMIT]:
            one = dict(data)
            for name, value in zip(lists, combo):        # и поля, куда провод разложен («Владелец» -> машина): тот же список
                one.update({key: value for key, item in data.items() if item is data[name]})
            outs.update(_action_one(run, kind, one))
        return ["fail"] if "fail" in outs or not outs else ["next"]
    return _action_one(run, kind, data)


def _screen(run, doc, node_id, kind):
    """«Экран: Показать» каждому адресату: инициатору, всем в игре или указанным (игрок, сессия, учётка, машина)."""
    from graph import sessions

    data = resolved(run, doc, node_id)
    if (data.get("who") or "player") == "list":
        found = sessions.audience(_as_list(data.get("targets")))
    elif data.get("scope") == "all":
        found = [(user, "") for user in sessions.online_users()]
    else:
        found = [(run.user, "")] if run.user is not None else []
    if not found:
        _log(run.graph, f"«{N.titled(kind, data)}»: некому показать", run.user)
        return ["fail"]
    data = {key: value for key, value in data.items() if key not in ("who", "scope", "targets")}
    outs = {out for user, where in found[:LIST_LIMIT] for out in _action_one(run, kind, data, user, where)}
    return ["fail"] if "fail" in outs else ["next"]


def _action_one(run, kind, data, user=None, where=""):
    from engine import actions as engine
    from engine.context import Ctx

    spec, action = N.action_of(kind, data)
    action = {key: _fill(_plain(value) if isinstance(value, float) else value, run) if key != "do" else value for key, value in action.items()}
    ctx = Ctx(source=f"сценарий {run.graph.slug}", user=user or run.user, box=_box(run) if user is None else None, depth=_depth.get(), where=where)
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


def _placement_act(run, doc, node_id, kind):
    """«Размещение: Изменить / Создать»: с каждым размещением на входе; «Размещение» на выходе — где файл теперь (одно или список, как вход)."""
    import posixpath

    from filesystem import placements
    from filesystem.layers import player
    from graph import entities

    data = resolved(run, doc, node_id)
    if kind.name == "act:layer":
        return _layer_act(run, node_id, kind, data)
    raw = data.get("placement")
    many = isinstance(raw, (list, tuple))
    keys = [str(k) for k in _as_list(raw) if str(k or "").strip()]
    create = kind.name == "act:placement.create"
    if create and not keys and not many:
        user, machine = entities._player(run, entities._key(data.get("player"))), entities._machine(entities._key(data.get("machine")))
        found = [(user, machine, _fill(str(data.get("path") or ""), run, keep=("login",)))] if user is not None and machine is not None else [None]
    else:
        found = [entities.parse_placement(key, run) for key in keys]
    item = None
    if data.get("item") not in (None, ""):
        from filesystem.models import Item

        item = Item.objects.filter(slug=entities._key(data.get("item"))).first() or Item.objects.filter(name__iexact=entities._key(data.get("item"))).first()
        if item is None:
            _log(run.graph, f"«{kind.label}»: нет объекта «{data.get('item')}»", run.user)
            return ["fail"]
    mode = data.get("variant") or "move"
    results, failed = [], not found
    for place in found:
        if place is None:
            failed = True
            continue
        user, machine, path = place
        try:
            if create:
                new = placements.add(user, machine, path, item) if item is not None else placements.create(user, machine, path, _fill(str(data.get("text") or ""), run))
            elif mode == "move":
                target = _fill(str(data.get("target") or ""), run, keep=("login",)).strip()
                if target.endswith("/"):
                    target += posixpath.basename(path)                      # в папку под тем же именем
                elif target and "/" not in target:
                    target = posixpath.join(posixpath.dirname(path), target)   # новое имя рядом
                new = placements.move(user, machine, path, target)
            elif mode == "replace":
                if item is None:
                    raise placements.PlacementError("не выбран новый объект")
                new = placements.replace(user, machine, path, item)
            elif mode == "trash":
                new = placements.trash(user, machine, path)
            elif mode == "purge":
                new = placements.purge(user, machine, path)
            elif mode in ("add_layer", "reset_layers"):
                view = entities._view(user, machine)
                if mode == "add_layer":
                    player.add(view, path, str(data.get("type") or ""), _fill(str(data.get("args") or ""), run))
                else:
                    player.reset(view, path)
                new = path
            else:
                new = placements.restore(user, machine, path, _fill(str(data.get("restore_to") or ""), run, keep=("login",)))
        except (placements.PlacementError, player.LayerError, ValueError, PermissionError, FileNotFoundError) as error:
            _log(run.graph, f"«{N.titled(kind, data)}»: {error}", run.user)
            failed = True
            continue
        results.append(entities.placement_key(user, machine.hostname, new) if new else "")
    value = results if many else (results[0] if results else "")
    run.state = {**(run.state or {}), "vals": {**((run.state or {}).get("vals") or {}), node_id: {"placement": value}}}
    return ["fail"] if failed else ["next"]


def _layer_act(run, node_id, kind, data):
    """«Слой: Изменить» со слоем или размещением (его верхним слоем), одним или списком. «Слой» на выходе — с каким слоем сделано."""
    from filesystem.layers import player
    from graph import entities

    raw = data.get("layer")
    many = isinstance(raw, (list, tuple))
    mode = data.get("variant") or "remove"
    results, failed = [], False
    keys = [str(k) for k in _as_list(raw) if str(k or "").strip()]
    for key in keys:
        head, mark, number = key.rpartition("#")
        place = entities.parse_placement(head if mark else key, run)
        if place is None:
            failed = True
            continue
        user, machine, path = place
        number = number if mark else ""
        base = entities.placement_key(user, machine.hostname, path)
        try:
            view = entities._view(user, machine)
            if mode in ("remove", "quiet"):
                path, done = player.remove(view, path, number, quiet=mode == "quiet")
                number = done[-1] if done else number
                base = entities.placement_key(user, machine.hostname, path)
            else:
                player.reset_attempts(view, path, number)
                number = number or player.top_id(view.get(path).state, view.get(path).progress)
        except (player.LayerError, ValueError, PermissionError, FileNotFoundError) as error:
            _log(run.graph, f"«{N.titled(kind, data)}»: {error}", run.user)
            failed = True
            continue
        results.append(f"{base}#{number}" if number else base)
    value = results if many else (results[0] if results else "")
    run.state = {**(run.state or {}), "vals": {**((run.state or {}).get("vals") or {}), node_id: {"layer": value}}}
    return ["fail"] if failed or not keys else ["next"]


def _state(machine, mode, data):
    """Новые значения дефектов машины для «Изменить состояние»: заполненные поля (задать или прибавить) или всё в ноль."""
    from machines.world import edits

    found = {}
    for name, _, _, top in N.STATE:
        if mode == "reset":
            found[name] = 0
            continue
        raw = str(data.get(name) if data.get(name) is not None else "").strip().replace(",", ".")
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            raise edits.EditError(f"не число: «{raw}»") from None
        if mode == "add":
            value += float(getattr(machine, name) or 0)
        value = max(0.0, value if top is None else min(float(top), value))
        found[name] = value
    return found


def _machine_act(run, node_id, kind, data):
    """Машина и учётки: «Изменить», «Изменить учётку», «Доступ к учётке», «Создать или удалить учётку». С каждой из списка."""
    from graph import entities
    from machines.world import edits

    mode = data.get("variant") or ""
    fill = lambda name: _fill(str(data.get(name) or ""), run).strip()        # noqa: E731
    items = lambda name: [str(v).strip() for v in _as_list(data.get(name)) if str(v or "").strip()]      # noqa: E731
    number = lambda name: int(float(data.get(name))) if str(data.get(name) or "").strip().lstrip("-").replace(".", "", 1).isdigit() else None  # noqa: E731
    results, failed, many = [], False, False
    try:
        if kind.name == "act:machine.change":
            raw = data.get("machine")
            for key in _as_list(raw):
                machine = entities._machine(entities._key(key))
                if machine is None:
                    raise edits.EditError(f"нет машины «{key}»")
                what = mode or "name"
                if what == "display":
                    edits.change_machine(machine, display=(data.get("display") or "on") != "off")
                    continue
                if what == "seats":
                    raw = str(data.get("seats") if data.get("seats") is not None else "").strip()
                    edits.change_machine(machine, seats=int(float(raw)) if raw.replace(".", "", 1).isdigit() else None)
                    continue
                value = str(data.get(what) or "") if what == "note" else fill(what)
                if what == "host_key" and not value:
                    value = "*"                                         # пусто — новый случайный отпечаток
                if what != "note" and not value:
                    raise edits.EditError("не задано новое значение")
                edits.change_machine(machine, **{"booted" if what == "booted" else what: _fill(value, run) if what == "note" else value})
            if not _as_list(raw):
                raise edits.EditError("не выбрана машина")
        elif kind.name == "act:machine.state":
            raw = data.get("machine")
            if not _as_list(raw):
                raise edits.EditError("не выбрана машина")
            for key in _as_list(raw):
                machine = entities._machine(entities._key(key))
                if machine is None:
                    raise edits.EditError(f"нет машины «{key}»")
                edits.change_machine(machine, **_state(machine, data.get("mode") or "set", data))
        elif kind.name == "act:account.manage" and (mode or "create") == "create":
            machine = entities._machine(entities._key(data.get("machine")))
            if machine is None:
                raise edits.EditError("не выбрана машина")
            owner = None
            if data.get("owner") == "player":
                if run.user is None:
                    raise edits.EditError("«Инициатора» без игрока")
                owner = run.user
            profile = edits.create(machine, fill("login"), name=fill("name"), endpoints=items("points"), password=str(data.get("password") or ""),
                                   mail=fill("mail"), groups=items("groups"), user=owner)
            results.append(edits.account_key(profile))
        else:
            raw = data.get("account")
            many = isinstance(raw, (list, tuple))
            keys = [str(k) for k in _as_list(raw) if str(k or "").strip()]
            if not keys:
                raise edits.EditError("не выбрана учётка")
            for key in keys:
                profile = edits.account(key)
                if profile is None:
                    _log(run.graph, f"«{N.titled(kind, data)}»: нет учётки {key}", run.user)
                    failed = True
                    continue
                if kind.name == "act:account.manage":
                    edits.delete(profile)
                elif kind.name == "act:account.access":
                    everyone = data.get("scope") == "all"
                    user = None if everyone else entities._player(run, entities._key(data.get("player")))
                    if not everyone and user is None:
                        raise edits.EditError("нет игрока: «игроку» без игрока")
                    if (mode or "block") == "block":
                        edits.block(profile, user, number("minutes") or 10, fill("text"))
                    else:
                        edits.unblock(profile, user, everyone=everyone)
                else:
                    mode = mode or "mail"
                    if mode == "mail":
                        edits.set_mail(profile, fill("mail"))
                    elif mode == "password":
                        edits.set_password(profile, str(data.get("password") or ""))
                    elif mode == "keys":
                        edits.set_keys(profile, fill("keys"))
                    elif mode == "points_add":
                        edits.add_endpoints(profile, items("points"))
                    elif mode == "points_remove":
                        edits.remove_endpoints(profile, items("points"))
                    elif mode == "groups_add":
                        edits.add_groups(profile, items("groups"))
                    elif mode == "groups_remove":
                        edits.remove_groups(profile, items("groups"))
                    elif mode == "token_add":
                        results.append(edits.create_token(profile, number("uses"), number("minutes")))
                    elif mode == "token_remove":
                        edits.delete_tokens(profile, items("tokens"))
    except edits.EditError as error:
        _log(run.graph, f"«{N.titled(kind, data)}»: {error}", run.user)
        failed = True
    out = "account" if kind.name == "act:account.manage" else "token"
    value = results if many else (results[0] if results else "")
    run.state = {**(run.state or {}), "vals": {**((run.state or {}).get("vals") or {}), node_id: {out: value}}}
    return ["fail"] if failed else ["next"]


def _disk_act(run, node_id, kind, data):
    """«Машина: Изменить диск»: подключить диск, подключить сетевой, отключить — у машины для всех."""
    from graph import entities
    from machines.world import disks, edits

    mode = data.get("variant") or "attach"
    key = lambda name: entities._key(data.get(name))       # noqa: E731
    result, failed = "", False
    try:
        if mode == "detach" and key("mount"):
            found = disks.parse(key("mount"))
            if found is None:
                raise disks.DiskError(f"нет точки «{key('mount')}»")
            machine, point = found
        else:
            machine, point = entities._machine(key("machine")), _fill(key("point"), run)
            if machine is None:
                raise disks.DiskError("не выбрана машина")
        if mode == "attach":
            result = disks.attach(machine, disks.volume(key("volume")), point, _fill(key("folder"), run), _truth(data.get("read_only")))
        elif mode == "remote":
            account = edits.account(key("account")) if key("account") else None
            host = entities._machine(key("host"))
            if account is None and host is not None:
                from machines.network import connection

                account = connection.account_of(host, "guest")
            result = disks.attach_remote(machine, host, _fill(key("path"), run), account, point, _truth(data.get("read_only")))
        else:
            volume = disks.volume(key("volume")) if key("volume") else None
            if key("volume") and volume is None:
                raise disks.DiskError(f"нет диска «{key('volume')}»")
            if not disks.detach(machine, point, volume):
                raise disks.DiskError("там ничего не подключено")
            result = disks.key_of(machine, point) if point else ""
    except disks.DiskError as error:
        _log(run.graph, f"«{N.titled(kind, data)}»: {error}", run.user)
        failed = True
    run.state = {**(run.state or {}), "vals": {**((run.state or {}).get("vals") or {}), node_id: {"mount": result}}}
    return ["fail"] if failed else ["next"]


def _execute(run, doc, node_id, sock):
    """Выполнить ноду; вернуть выходы, по которым идти дальше."""
    import random

    kind, data = doc.kind(node_id), resolved(run, doc, node_id)
    name = kind.name
    if kind.group in N.NOUNS:
        return [] if kind.start_only else _noun_wait(run, doc, node_id, kind)
    if name in N.PLACEMENT_ACTS:
        return _placement_act(run, doc, node_id, kind)
    if name in ("act:character.say", "act:character.reply"):
        return _character_act(run, kind, data)
    if name == "act:session.close":
        from graph import sessions

        if sessions.close(run, _as_list(data.get("session"))):
            return ["next"]
        _log(run.graph, f"«{kind.label}»: нет такой сессии", run.user)
        return ["fail"]
    if name == "act:machine.disk":
        return _disk_act(run, node_id, kind, data)
    if name in N.MACHINE_ACTS:
        return _machine_act(run, node_id, kind, data)
    if name in N.OFFER_ACTS:
        from graph import offers

        return offers.act(run, node_id, kind, data)
    if name == "act:screen":
        return _screen(run, doc, node_id, kind)
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
    if name == "wait_cond":
        return _wait_cond(run, doc, node_id)
    if name == "check":
        return ["yes" if _holds(data.get("condition"), run) else "no"]
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
            if data.get("cycle") == "stop" and mark.value >= _count(data, "count"):
                return ["over"]                     # все ветки пройдены, по кругу не идём
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
    if name == "join":
        return _join(run, doc, node_id, data, sock)
    if name == "crew":
        return _crew(run, doc, node_id, data)
    if name == "branch_owner":
        return _owner(run, doc, data)
    if name == "branch_unowner":
        run.owner, run.crew = None, None
        if run.pk:
            Run.objects.filter(pk=run.pk).update(owner=None, crew=None)
        return ["next"]
    if name == "branch_gate":
        return _gate(run, doc, node_id, data)
    if name == "claim":
        return _claim(run, data)
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
    if run.pk:
        _cancel_children(run)


def _cancel_children(run):
    """Ветки «Ожидание веток» и «Наблюдения», которые ещё идут, снимаются вместе с их ожиданиями (и их ветки — тоже).
    Ветки «Ветвления» живут сами: они отцепляются от родителя, когда он заканчивается."""
    for child in Run.objects.filter(parent=run, status=Run.Status.RUNNING):
        if (child.state or {}).get("fork"):
            Run.objects.filter(pk=child.pk).update(parent=None)
            continue
        _finish(child, "cancelled")
        child.save(update_fields=["status", "outcome", "ended_at"])


# ---------- «Ожидание веток»: ветка на элемент, «Конец ветки» возвращает её ----------

_live = {}                                   # потоки, которые сейчас запускают ветки: вернувшиеся сразу пишут в них, а не в базу


def _item_of(value):
    """Кто такой элемент: {"user": pk, "account": логин@хост} — игрок, учётка или сессия (игрок/логин@хост); иначе пусто."""
    from django.contrib.auth import get_user_model

    from machines.world import edits

    text = str(value or "").strip()
    head, slash, rest = text.partition("/")
    user_name, account = (head, rest) if slash else ("" if "@" in text else text, text if "@" in text else "")
    found = {}
    if user_name:
        user = get_user_model().objects.filter(username__iexact=user_name).first()
        if user is not None:
            found["user"] = user.pk
    if account and edits.account(account) is not None:
        found["account"] = account
    return found


def _branches_met(state, data):
    done, total = len(state.get("finished") or []), state.get("total") or 0
    mode = data.get("mode") or "all"
    if mode == "first":
        return done >= 1
    if mode == "count":
        return done >= min(_count(data, "need", 2) if str(data.get("need") or "").isdigit() else 2, total)
    return done >= total


def _each(run, doc, node_id, queue):
    """Запустить ветки «Ожидание веток»: по потоку на элемент, со своим элементом (игрок — инициатор, учётка — место)."""
    from django.contrib.auth import get_user_model

    data = resolved(run, doc, node_id)
    items = _as_list(input_of(run, doc, node_id, "list"))[:LIST_LIMIT]
    start_at = next((nid for nid, node in doc.nodes.items() if nid.startswith(node_id + "/") and node.get("type") == "branch_in"
                     and nid.count("/") == node_id.count("/") + 1), None)
    state = {"total": len(items), "finished": []}
    vals = {**((run.state or {}).get("vals") or {}), node_id: {"finished": [], "first": ""}}
    run.state = {**(run.state or {}), "vals": vals, "each": {**((run.state or {}).get("each") or {}), node_id: state}}
    if not items or start_at is None:
        if start_at is None and items:
            _log(run.graph, "«Ожидание веток»: внутри нет «Начала ветки»", run.user)
        queue.extend(doc.next(node_id, "done"))
        return
    hold = Wait.objects.create(run=run, user=run.user, node=node_id, out="done", kind=Wait.Kind.TIME, until=None)   # ждёт ветки
    run.save(update_fields=["state", "ctx", "user"])
    _live[run.pk] = run
    try:
        for index, value in enumerate(items, 1):
            if _branches_met(run.state["each"][node_id], data):
                break                                            # «Любой»/«По количеству» уже набрали — остальные не запускаем
            item = _item_of(value)
            user = get_user_model().objects.filter(pk=item["user"]).first() if item.get("user") else run.user
            ctx = dict(run.ctx or {})
            if item.get("account"):
                login, _, host = item["account"].partition("@")
                ctx.update(host=host, login=login)
            child = Run.objects.create(graph=run.graph, user=user, node=start_at, ctx=ctx, parent=run,
                                       state={"vals": {**vals, start_at: {"item": value, "index": index}}, "item": item,
                                              "each": node_id, "value": value})
            child.graph = run.graph
            _hit(child, start_at)
            advance(child, doc.next(start_at, "next"))
    finally:
        _live.pop(run.pk, None)
    if _branches_met(run.state["each"][node_id], data):
        hold.delete()
        _cancel_children(run)
        queue.extend(doc.next(node_id, "done"))


def _head_of(doc, node_id):
    """«Начало ветки» внутри «Ветвления»."""
    return next((nid for nid, node in doc.nodes.items() if nid.startswith(node_id + "/") and node.get("type") == "branch_head"
                 and nid.count("/") == node_id.count("/") + 1), None)


def _branch(graph, doc, node_id, start_at, parent=None, vacancy=False):
    """Новая ветка «Ветвления»: свободная (без владельца), идёт от «Начала ветки» до первого ожидания."""
    child = Run.objects.create(graph=graph, user=None, node=start_at, ctx={}, parent=parent,
                               state={"vals": {}, "fork": node_id, **({"vacancy": True} if vacancy else {})})
    child.graph = graph
    _hit(child, start_at)
    advance(child, doc.next(start_at, "next"))
    return child


def _room(spawn, data):
    """Есть ли место для ещё одной занятой ветки: «Веток всего» не исчерпано."""
    total = _int(data, "total")
    return not total or spawn.taken < total


def _open_vacancy(graph, doc, node_id, parent=None):
    """Открыть свободную ветку «Ветвления» с повтором, если повтор включён, есть место и свободной ветки ещё нет."""
    from graph.models import Branching

    start_at = _head_of(doc, node_id)
    if start_at is None:
        return None
    with transaction.atomic():
        spawn, _ = Branching.objects.select_for_update().get_or_create(graph=graph, node=node_id)
        if not spawn.open or not _room(spawn, doc.data(node_id)):
            return None
        if Run.objects.filter(graph=graph, status=Run.Status.RUNNING, state__fork=node_id, state__vacancy=True).exists():
            return None
        return _branch(graph, doc, node_id, start_at, parent, vacancy=True)


def _branching(run, doc, node_id, queue):
    """«Ветвление»: родитель идёт «Дальше» сразу, рядом рождается ветка (без повтора) или открывается вакансия (с повтором)."""
    queue.extend(doc.next(node_id, "next"))
    start_at = _head_of(doc, node_id)
    if start_at is None:
        _log(run.graph, "«Ветвление»: внутри нет «Начала ветки»", run.user)
        return
    if doc.data(node_id).get("repeat") == "yes":
        _open_vacancy(run.graph, doc, node_id, run)
    else:
        _branch(run.graph, doc, node_id, start_at, run)


def _vacancy_accepts(wait, event):
    """Вакансия слышит игрока, если у него ещё не набралось «На инициатора» веток."""
    from graph.models import Branching

    node_id = (wait.run.state or {}).get("fork")
    if event.user is None or not node_id:
        return True
    spawn = Branching.objects.filter(graph=wait.run.graph, node=node_id).first()
    per = _int(doc_of(wait.run.graph).data(node_id), "per", 1)
    return spawn is None or int((spawn.users or {}).get(str(event.user.pk), 0)) < per


def _occupy(run, event):
    """Первый триггер вакансии сработал: ветка занята, и сразу (в той же транзакции) открывается следующая вакансия."""
    from graph.models import Branching

    node_id = (run.state or {}).get("fork")
    run.state = {**(run.state or {}), "vacancy": False}
    Run.objects.filter(pk=run.pk).update(state=run.state)
    spawn, _ = Branching.objects.select_for_update().get_or_create(graph=run.graph, node=node_id)
    spawn.taken += 1
    if event is not None and event.user is not None:
        spawn.users = {**(spawn.users or {}), str(event.user.pk): int((spawn.users or {}).get(str(event.user.pk), 0)) + 1}
    spawn.save(update_fields=["taken", "users"])
    _open_vacancy(run.graph, doc_of(run.graph), node_id)


def _gate(run, doc, node_id, data):
    """«Повтор ветвления»: отключить (свободная ветка снимается) или включить (свободная ветка появляется снова)."""
    from graph.models import Branching

    forks = [src for (dst, name), (src, _) in doc.refs.items() if dst == node_id and name == "branches"]
    if not forks:
        _log(run.graph, "«Повтор ветвления»: не подключено ветвление", run.user)
    for fork in forks:
        spawn, _ = Branching.objects.get_or_create(graph=run.graph, node=fork)
        if data.get("mode") == "open":
            Branching.objects.filter(pk=spawn.pk).update(open=True)
            _open_vacancy(run.graph, doc, fork)
            continue
        Branching.objects.filter(pk=spawn.pk).update(open=False)
        for free in Run.objects.filter(graph=run.graph, status=Run.Status.RUNNING, state__fork=fork, state__vacancy=True):
            _finish(free, "cancelled")
            free.save(update_fields=["status", "outcome", "ended_at"])
    return ["next"]


def _owner(run, doc, data):
    """«Ветка: Назначить владельца»: игрок (пусто — инициатор) или группа инициаторов."""
    from graph import crews, entities

    if data.get("who") == "crew":
        name = str(data.get("crew") or "").strip()
        if not name:
            _log(run.graph, "«Назначить владельца»: не задана группа", run.user)
            return ["next"]
        run.owner, run.crew = None, crews.crew_of(run.graph, name)
    else:
        user = entities._player(run, entities._key(data.get("player")))
        if user is None:
            _log(run.graph, "«Назначить владельца»: нет игрока", run.user)
            return ["next"]
        run.owner, run.crew = user, None
    if run.pk:
        Run.objects.filter(pk=run.pk).update(owner=run.owner, crew=run.crew)
    return ["next"]


def _crew(run, doc, node_id, data):
    """«Группа инициаторов»: добавить / убрать / закрыть / открыть вступление; «Закрыта», если добавить не вышло."""
    from graph import crews, entities

    name = str(data.get("name") or "").strip()
    if not name:
        _log(run.graph, "«Группа инициаторов»: не задано имя группы", run.user)
        return []
    mode = data.get("mode") or "add"
    user = entities._player(run, entities._key(data.get("player")))
    out = "next"
    if mode in ("add", "remove") and user is None:
        _log(run.graph, "«Группа инициаторов»: нет игрока", run.user)
        return ["full"] if mode == "add" else ["next"]
    if mode == "add":
        out = "next" if crews.join(run.graph, name, user, _int(data, "limit")) == "joined" else "full"
    elif mode == "remove":
        crews.leave(run.graph, name, user)
    else:
        crews.set_closed(run.graph, name, mode == "close")
    found = crews.members(run.graph, name)
    run.state = {**(run.state or {}), "vals": {**((run.state or {}).get("vals") or {}), node_id: {"count": len(found), "members": found}}}
    return [out]


def _claim(run, data):
    """«Тег: Поставить, если нет»: поставить, если ещё не стоит (атомарно). «set» — это мы, «already» — уже стоял."""
    from engine import values

    name = str(data.get("name") or "").strip()
    owner, oid, _ = values.target({"owner": "player" if data.get("scope") == "player" else "world"}, run.user)
    user = run.user if data.get("scope") == "player" else None
    try:
        took = values.set_tag(owner, oid, name, True, user=user, source="scenario")
    except values.BadValue as error:
        _log(run.graph, f"«Тег: Поставить, если нет»: {error}", run.user)
        return ["already"]
    return ["set" if took else "already"]


def _listeners(doc, node_id):
    """Триггеры «Наблюдения»: внутри его группы, без входящего провода потока, с подключёнными выходами-событиями."""
    depth = node_id.count("/") + 1
    found = []
    for nid in doc.nodes:
        if not nid.startswith(node_id + "/") or nid.count("/") != depth or nid in doc.fed:
            continue
        kind = doc.kind(nid)
        if kind is None or kind.group not in N.NOUNS or kind.start_only:
            continue
        found += [(nid, out, N.event_of(kind, out)) for out in doc.wired(nid) if N.event_of(kind, out)]
    return found


def _watch_open(run, doc, node_id):
    """Открыть наблюдение: поток стоит на ноде, внутренние триггеры ловят (ожидания-«@watch» не снимаются при срабатывании)."""
    if Wait.objects.filter(run=run, node=node_id, out="done").exists():
        return
    vals = {**((run.state or {}).get("vals") or {}), node_id: {"count": 0, "initiators": []}}
    run.state = {**(run.state or {}), "vals": vals}
    Wait.objects.create(run=run, user=run.user, node=node_id, out="done", kind=Wait.Kind.TIME, until=None)       # держит поток
    for nid, out, event in _listeners(doc, node_id):
        Wait.objects.create(run=run, user=run.user, node=nid, out=out, kind=Wait.Kind.EVENT, event=event, anyone=True,
                            data={"@watch": node_id})
    if not _listeners(doc, node_id):
        _log(run.graph, "«Наблюдение»: внутри нет триггеров — ловить нечего", run.user)


def open_watches(graph):
    """Наблюдения без провода во «Когда» идут с включения сценария: держит их свой поток (без инициатора)."""
    if not graph.active:
        return
    doc = doc_of(graph)
    fed_in = {dst for targets in doc.flow.values() for dst, inp in targets if inp == "in"}
    for node_id, node in doc.nodes.items():
        if node.get("type") != "watch" or node_id in fed_in or node.get("_inline"):
            continue
        if Run.objects.filter(graph=graph, status=Run.Status.RUNNING, waits__node=node_id, waits__out="done").exists():
            continue
        run = Run.objects.create(graph=graph, user=None, node=node_id, ctx={})
        run.graph = graph
        _watch_open(run, doc, node_id)
        run.save(update_fields=["state"])


def _watch_fire(wait, event):
    """Событие для «Наблюдения»: если «Пока» верно — новая ветка с инициатором события от этого триггера."""
    with transaction.atomic():
        holder = Run.objects.select_for_update().select_related("graph").filter(pk=wait.run_id).first()
        if holder is None or holder.status != Run.Status.RUNNING:
            return None
        node_id = (wait.data or {}).get("@watch")
        doc = doc_of(holder.graph)
        condition = resolved(holder, doc, node_id).get("while")
        if condition not in (None, "") and not _holds(condition, Run(graph=holder.graph, user=event.user, ctx=_ctx_of(event), state={})):
            return None
        vals = dict((holder.state or {}).get("vals") or {})
        mine = dict(vals.get(node_id) or {"count": 0, "initiators": []})
        name = event.user.get_username() if event.user is not None else ""
        mine["count"] = int(mine.get("count") or 0) + 1
        if name and name not in (mine.get("initiators") or []):
            mine["initiators"] = [*(mine.get("initiators") or []), name]
        vals[node_id] = mine
        holder.state = {**(holder.state or {}), "vals": vals}
        holder.save(update_fields=["state"])
        child = Run.objects.create(graph=holder.graph, user=event.user, node=wait.node, ctx=_ctx_of(event), parent=holder,
                                   state={"vals": vals, "watch": node_id})
    child.graph = holder.graph
    capture(child, wait.node, event)
    _hit(child, wait.node)
    return advance(child, doc.next(wait.node, wait.out))


def _close_watch(holder, doc, node_id, keep=None):
    """Снять наблюдение у потока holder: ловцы и держатель убираются, ветки снимаются (кроме keep) или доживают."""
    inner = [nid for nid in doc.nodes if nid.startswith(node_id + "/")]
    Wait.objects.filter(run=holder).filter(Q(node=node_id) | Q(node__in=inner, data__has_key="@watch")).delete()
    branches = Run.objects.filter(parent=holder, status=Run.Status.RUNNING, state__watch=node_id)
    branches.filter(pk=keep).update(parent=None)                     # ветка, которая сняла, идёт дальше сама по себе
    if (resolved(holder, doc, node_id).get("branches") or "cancel") == "cancel":
        for child in branches.exclude(pk=keep):
            _finish(child, "cancelled")
            child.save(update_fields=["status", "outcome", "ended_at"])
    else:
        branches.update(parent=None)                                 # доживают: дальше их не снимает и конец истории


def _watch_stop(run, doc, node_id, queue):
    """Вход «Снять наблюдение»: у всех потоков этого сценария, которые наблюдают на этой ноде; дальше — «Готово»."""
    holders = Run.objects.filter(graph=run.graph, status=Run.Status.RUNNING, waits__node=node_id, waits__out="done").distinct()
    for holder in list(holders.select_related("graph")):
        if holder.pk == run.pk:
            _close_watch(run, doc, node_id)
            queue.extend(doc.next(node_id, "done"))
            continue
        _close_watch(holder, doc, node_id)
        advance(holder, doc.next(node_id, "done"))


def _watch_stop_inside(child, doc):
    """Нода «Снять наблюдение» в ветке: снять её наблюдение; сама ветка идёт дальше."""
    node_id = (child.state or {}).get("watch")
    holder = Run.objects.select_related("graph").filter(pk=child.parent_id, status=Run.Status.RUNNING).first() if node_id else None
    if holder is None:
        _log(child.graph, "«Снять наблюдение» вне наблюдения", child.user)
        return
    _close_watch(holder, doc, node_id, keep=child.pk)
    child.parent_id = None
    advance(holder, doc.next(node_id, "done"))


def _branch_done(child):
    """Ветка дошла до «Конца ветки»: записать её в «Успели» у родителя; набралось нужное — родитель идёт в «Готово»."""
    state = child.state or {}
    node_id = state.get("each")
    if child.parent_id is None or not node_id:
        return
    parent = _live.get(child.parent_id)
    live = parent is not None
    with transaction.atomic():
        if not live:
            parent = Run.objects.select_for_update().select_related("graph").filter(pk=child.parent_id).first()
            if parent is None or parent.status != Run.Status.RUNNING:
                return
        each = dict(((parent.state or {}).get("each") or {}).get(node_id) or {})
        if each.get("closed"):
            return
        each["finished"] = [*(each.get("finished") or []), state.get("value")]
        vals = dict((parent.state or {}).get("vals") or {})
        vals[node_id] = {"finished": list(each["finished"]), "first": each["finished"][0]}
        doc = doc_of(parent.graph)
        met = _branches_met(each, resolved(parent, doc, node_id))
        if met:
            each["closed"] = True
        parent.state = {**(parent.state or {}), "vals": vals, "each": {**((parent.state or {}).get("each") or {}), node_id: each}}
        if live:
            return                                   # ветки ещё запускаются: «Готово» решит сам запуск
        parent.save(update_fields=["state"])
        if not met:
            return
        Wait.objects.filter(run=parent, node=node_id).delete()
    _cancel_children(parent)
    advance(parent, doc.next(node_id, "done"))


def advance(run, items):
    """Пройти от входов items [(нода, вход)] до ожиданий и концов."""
    doc = doc_of(run.graph)
    _drain(run, doc, deque(items), [0])
    if run.status == Run.Status.RUNNING and not Wait.objects.filter(run=run).exists():
        _finish(run, run.outcome or "")
    run.save(update_fields=["status", "outcome", "ended_at", "ctx", "state", "owner", "crew"])
    return run


def _drain(run, doc, queue, steps):
    """Очередь нод до конца. «Ожидание веток» запускает ветки (по потоку на элемент) и ждёт их «Конца ветки»."""
    while queue and run.status == Run.Status.RUNNING:
        node_id, sock = queue.popleft()
        kind = doc.kind(node_id)
        if kind is None or kind.name in ("note", "frame") or kind.group in (N.DATA, N.ENTITY, N.ATTR):
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
        if kind.name == "each":
            _each(run, doc, node_id, queue)
            continue
        if kind.name == "branching":
            _branching(run, doc, node_id, queue)
            continue
        if kind.name == "branch_out":
            _branch_done(run)
            if (run.state or {}).get("fork") or (run.state or {}).get("each"):
                _finish(run)                                 # конец ветки закрывает её целиком, и недождавшиеся альтернативные ожидания тоже
            continue
        if kind.name == "watch":
            if sock == "stop":
                _watch_stop(run, doc, node_id, queue)
            else:
                _watch_open(run, doc, node_id)
            continue
        if kind.name == "watch_stop":
            _watch_stop_inside(run, doc)
            queue.extend(doc.next(node_id, "next"))
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

DEFAULT_REPEAT = {"manual": "always", "while": "always", "on:time": "always", "on:schedule": "always",
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
        runs = Run.objects.filter(graph=graph, node=node_id)
        mine = runs.filter(user=user)                                     # «один раз» и «снова после конца» — у каждого игрока свои
        if repeat == "game" and runs.exists():
            return None
        if repeat == "once" and mine.exists():
            return None
        if repeat == "end" and mine.filter(status=Run.Status.RUNNING).exists():
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
        if wait.kind == Wait.Kind.CONDITION:
            _met(run, wait.node)
        if (run.state or {}).get("vacancy"):
            _occupy(run, event)                      # свободную ветку заняли: рядом открывается следующая
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
    for wait in Wait.objects.filter(run__status=Run.Status.RUNNING, data__has_key="placement"):
        wanted = wait.data.get("placement")
        moved = [new if w == old else w for w in wanted] if isinstance(wanted, list) else (new if wanted == old else wanted)
        if moved != wanted:
            wait.data = {**wait.data, "placement": moved}
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
        if event.user is not None:                                   # поток с владельцем двигает только владелец (игрок или группа)
            waits = waits.filter(Q(run__owner__isnull=True, run__crew__isnull=True) | Q(run__owner=event.user)
                                 | Q(run__crew__members=event.user)).distinct()
        # событие без игрока (сигнал всем, метка мира, момент, машина) будит ждущих у всех
        for wait in list(waits.select_related("run__graph")):
            doc = doc_of(wait.run.graph)
            kind = doc.kind(wait.node)
            data = {**doc.data(wait.node), **(wait.data or {})}
            if kind is not None and kind.name == N.USED_OFFER:
                from graph import offers

                data = offers.match_data(wait.run.graph, doc, wait.node, data)
            account = (wait.data or {}).get("@account")
            if account and f"{event.login}@{event.host}".lower() != str(account).lower():
                continue
            if (wait.run.state or {}).get("vacancy") and not _vacancy_accepts(wait, event):
                continue                                 # у игрока уже набралось веток
            if (wait.data or {}).get("@watch"):
                if kind is not None and kind.match is not None and kind.match(data, wait.out, event):
                    touched += bool(_watch_fire(wait, event))
                continue
            if kind is not None and kind.match is not None and kind.match(data, wait.out, event):
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
            if kind is not None and kind.name == N.USED_OFFER:
                from graph import offers

                data = offers.match_data(row.graph, doc, row.node, data)
            if kind is not None and kind.match is not None and kind.match(data, row.out, event):
                touched += bool(start(row.graph, row.node, row.out, event.user, _ctx_of(event)))
        if event.name in ("file.moved", "file.deleted", "file.restored"):
            follow(event)
        touched += whiles(event)
    finally:
        _depth.reset(token)
    return touched


OUTCOMES = {"machine": ("machine.login", "machine.denied"), "net.request": ("net.request", "net.denied"),       # «как обычно»: чем кончилось,
            "net.download": ("net.download", "net.denied")}                                                     # когда решила сама вещь


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


def start_manual(graph, node_id, user=None, author=None):
    """Кнопка автора «Вручную»: поток мира или (для проверки) за игрока user; author — кто нажал (выход «Автор»)."""
    kind = doc_of(graph).kind(node_id)
    if kind is None or kind.name != "manual":
        raise ValueError("это не нода «Вручную»")
    name = author.get_username() if author is not None else ""
    return start(graph, node_id, "fire", user, {"event": N.MANUAL_EVENT, "data": {"author": name}}, repeat="always")


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
    if (data.get("mode") or "daily") == "once":
        from graph import times

        moment = times.parse(data.get("at"), words=False)
        if moment is None:
            raise ValueError(f"дата «{data.get('at')}»: нужно ГГГГ-ММ-ДД ЧЧ:ММ")
        return moment
    hour, minute = _clock(data.get("at"))
    target = game.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target <= game else target - timedelta(days=1)


def _time_starts():
    from machines.world import chrono

    game = chrono.game_now()
    fired = 0
    for row in list(Start.objects.filter(event=N.TIME_EVENT, graph__active=True).select_related("graph")):
        doc = doc_of(row.graph)
        kind = doc.kind(row.node)
        data = resolved(Run(graph=row.graph, user=None, ctx={}, state={}), doc, row.node) if kind is not None else doc.data(row.node)
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
        fired += bool(start(row.graph, row.node, "fire", None, {"event": N.TIME_EVENT}))       # время — ход мира, без игрока
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
    done += whiles()
    return done


def whiles(event=None):
    """«Пока» и действия с условием во «Когда»: пересчитать условия, на смене — сработать. event — что случилось (None — тик).
    Условие игрока считается для игрока события (событие без игрока — для всех, у кого оно уже считалось), условие мира — всегда."""
    rows = {}
    for row in Start.objects.filter(event=N.WHILE_EVENT, graph__active=True).select_related("graph"):
        rows.setdefault((row.graph_id, row.node), (row.graph, set()))[1].add(row.out)
    ctx = _ctx_of(event) if event is not None else {}
    done = 0
    for (_, node_id), (graph, outs) in rows.items():
        doc = doc_of(graph)
        kind = doc.kind(node_id)
        if kind is None:
            continue
        bound = N.BIND in outs
        if bound or doc.data(node_id).get("scope") == "world":
            users = [None]
        elif event is not None and event.user is not None:
            users = [event.user]
        else:
            users = [mark.user for mark in Mark.objects.filter(graph=graph, node=node_id).exclude(user=None).select_related("user")]
        for user in users:
            run = Run(graph=graph, user=user, ctx=ctx, state={})
            value = resolved(run, doc, node_id).get("in" if bound else "condition")
            now = value not in (None, "") and _holds(value, run)
            with transaction.atomic():
                mark, _ = Mark.objects.select_for_update().get_or_create(graph=graph, node=node_id, user=user)
                if bool(mark.value) == now:
                    continue
                mark.value = int(now)
                mark.save(update_fields=["value"])
            if bound:
                done += _bound(graph, doc, node_id, kind, now)
            elif ("true" if now else "false") in outs:
                done += bool(start(graph, node_id, "true" if now else "false", user, ctx))
    return done


def _bound(graph, doc, node_id, kind, now):
    """Действие с условием: стало верно — сделать выбранное, стало ложно — обратное (N.UNDO); дальше по его выходам."""
    variant = doc.data(node_id).get("variant") or kind.fields[0].options[0][0]
    if not now:
        variant = N.UNDO.get(kind.name, {}).get(variant)
        if variant is None:
            return 0
    run = Run.objects.create(graph=graph, user=None, node=node_id, ctx={})
    run.graph = graph
    _hit(run, node_id)
    outs = _action(run, doc, node_id, kind, {"variant": variant})
    advance(run, [step for out in outs for step in doc.next(node_id, out)])
    return 1
