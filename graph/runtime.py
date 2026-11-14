"""Исполнитель сценариев.

Событие (engine.events.emit) будит ждущие ветки и запускает старты: существительное без входящего провода. Прохождение идёт
по проводам потока, пока не упрётся в ожидание (событие, время, условие) или в конец. Время и условия двигает tick() из
middleware мира. Прохождение одного игрока в одном сценарии — Run; где стоят его ветки — Wait.

Действия выполняются словарём движка от имени игрока прохождения; учётка — та, на которой случилось событие (host, login).
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

DEPTH = 8          # сценарий → действие → событие → сценарий…
STEPS = 300        # нод за один проход: защита от цикла без ожидания
TICK = 15
_depth = contextvars.ContextVar("graph_depth", default=0)
_lock = threading.Lock()
_last = {"at": 0.0}


# ---------- документ ----------

class Doc:
    """Граф в удобном виде: ноды по id, провода потока из (нода, выход), ссылки во входы-поля."""

    def __init__(self, doc):
        doc = doc or {}
        self.nodes = {str(node.get("id")): node for node in doc.get("nodes") or [] if isinstance(node, dict) and node.get("id")}
        self.flow, self.refs, self.fed = {}, {}, set()
        for wire in doc.get("wires") or []:
            if not isinstance(wire, dict):
                continue
            src, out, dst, inp = str(wire.get("from")), str(wire.get("out")), str(wire.get("to")), str(wire.get("in"))
            if src not in self.nodes or dst not in self.nodes:
                continue
            if inp.startswith("f:"):
                self.refs[(dst, inp[2:])] = src
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
        return kind is not None and kind.group == N.NOUN and node_id not in self.fed

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


_docs = {}


def doc_of(graph):
    key = (graph.pk, graph.updated_at)
    found = _docs.get(graph.pk)
    if found is None or found[0] != key:
        found = (key, Doc(graph.doc))
        _docs[graph.pk] = found
    return found[1]


def rebuild_starts(graph):
    """Выписать старты: существительные без входа и события их подключённых выходов."""
    doc = Doc(graph.doc)
    rows = []
    for node_id in doc.nodes:
        if not doc.is_start(node_id):
            continue
        kind = doc.kind(node_id)
        for out in doc.wired(node_id):
            if out in kind.events:
                rows.append(Start(graph=graph, node=node_id, out=out, event=kind.events[out]))
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


def _holds(text, run, known=None):
    from secure.access import satisfied

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


def _noun_wait(run, doc, node_id, kind):
    data = doc.data(node_id)
    outs = [out for out in doc.wired(node_id) if out in kind.events]
    if data.get("past") and run.user is not None:
        from engine.models import Event

        for event in Event.objects.filter(user=run.user, name__in={kind.events[out] for out in outs})[:300]:
            for out in outs:
                if kind.events[out] == event.name and kind.match(data, out, event):
                    run.ctx = {**(run.ctx or {}), **_ctx_of(event), "host": event.host or run.ctx.get("host"), "login": event.login or run.ctx.get("login")}
                    return [out]
    for out in outs:
        Wait.objects.create(run=run, user=run.user, node=node_id, out=out, kind=Wait.Kind.EVENT, event=kind.events[out], anyone=bool(data.get("anyone")))
    if data.get("timeout") not in (None, "", 0, "0") and N.TIMEOUT in doc.wired(node_id):
        Wait.objects.create(run=run, user=run.user, node=node_id, out=N.TIMEOUT, kind=Wait.Kind.TIME, until=after(data.get("timeout")))
    return []


def _wait(run, doc, node_id):
    data = doc.data(node_id)
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

    spec, data = kind.spec, doc.data(node_id)
    action = {"do": spec.name}
    for item in spec.fields:
        source = doc.refs.get((node_id, item.name))
        if source is not None:
            src_kind = doc.kind(source)
            value = doc.data(source).get(src_kind.ref[1]) if src_kind and src_kind.ref else None
        else:
            value = data.get(item.name)
        if value not in (None, ""):
            action[item.name] = _fill(value, run)
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

    kind, data = doc.kind(node_id), doc.data(node_id)
    name = kind.name
    if kind.group == N.NOUN:
        return [] if kind.start_only else _noun_wait(run, doc, node_id, kind)
    if kind.group == N.ACTION:
        return _action(run, doc, node_id, kind)
    if name in ("reroute", "stage"):
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
            mark = _mark(run, node_id, run.user)
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


def _finish(run, outcome=""):
    run.status, run.outcome, run.ended_at = Run.Status.DONE, outcome, timezone.now()
    Wait.objects.filter(run=run).delete()


def advance(run, items):
    """Пройти от входов items [(нода, вход)] до ожиданий и концов."""
    doc = doc_of(run.graph)
    queue, steps = deque(items), 0
    while queue and run.status == Run.Status.RUNNING:
        node_id, sock = queue.popleft()
        kind = doc.kind(node_id)
        if kind is None or kind.name in ("note", "frame"):
            continue
        if doc.nodes[node_id].get("mute"):                 # выключенная нода пропускает поток насквозь (как M в Blender)
            if "next" in N.sockets(kind, doc.data(node_id), "out"):
                queue.extend(doc.next(node_id, "next"))
            continue
        steps += 1
        if steps > STEPS:
            _log(run.graph, f"больше {STEPS} нод за раз: цикл без ожидания? Прохождение остановлено", run.user)
            _finish(run, "aborted")
            break
        _hit(run, node_id)
        try:
            outs = _execute(run, doc, node_id, sock)
        except Exception as error:                   # noqa: BLE001 — сломанная нода не роняет игру
            log.exception("graph node %s failed", node_id)
            _log(run.graph, f"нода {kind.label}: {error}", run.user)
            outs = []
        for out in outs:
            queue.extend(doc.next(node_id, out))
    if run.status == Run.Status.RUNNING and not Wait.objects.filter(run=run).exists():
        _finish(run, run.outcome or "")
    run.save(update_fields=["status", "outcome", "ended_at", "ctx", "state"])
    return run


# ---------- старт и пробуждение ----------

DEFAULT_REPEAT = {"time": "always", "manual": "always", "moment": "always"}


def start(graph, node_id, out, user=None, ctx=None, repeat=None):
    """Запустить прохождение со старта node_id по выходу out. Возвращает Run или None (по правилу повтора не нужно)."""
    doc = doc_of(graph)
    kind = doc.kind(node_id)
    if kind is None:
        return None
    repeat = repeat or doc.data(node_id).get("repeat") or DEFAULT_REPEAT.get(kind.name, "once")
    with transaction.atomic():
        Graph.objects.select_for_update().filter(pk=graph.pk).first()      # два события сразу: правило повтора видит одно
        runs = Run.objects.filter(graph=graph, user=user, node=node_id)
        if repeat == "once" and runs.exists():
            return None
        if repeat == "end" and runs.filter(status=Run.Status.RUNNING).exists():
            return None
        run = Run.objects.create(graph=graph, user=user, node=node_id, ctx=ctx or {})
    run.graph = graph
    _hit(run, node_id)
    return advance(run, doc.next(node_id, out))


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
            run.ctx = {**ctx, "event": event.name, "data": {**(ctx.get("data") or {}), **(event.data or {})},
                       "host": ctx.get("host") or event.host, "login": ctx.get("login") or event.login}
    return advance(run, doc_of(run.graph).next(wait.node, wait.out))


def dispatch(event):
    """Событие из engine.events.emit: разбудить ожидания и запустить старты. Возвращает число затронутых прохождений."""
    depth = _depth.get()
    if depth >= DEPTH:
        return 0
    token = _depth.set(depth + 1)
    touched = 0
    try:
        waits = Wait.objects.filter(kind=Wait.Kind.EVENT, event=event.name, run__status=Run.Status.RUNNING, run__graph__active=True)
        waits = waits.filter(Q(user=event.user) | Q(anyone=True)) if event.user is not None else waits.filter(Q(user__isnull=True) | Q(anyone=True))
        for wait in list(waits.select_related("run__graph")):
            kind = doc_of(wait.run.graph).kind(wait.node)
            if kind is not None and kind.match is not None and kind.match(doc_of(wait.run.graph).data(wait.node), wait.out, event):
                touched += bool(resume(wait, event))
        if event.user is not None:
            for wait in list(Wait.objects.filter(kind=Wait.Kind.CONDITION, user=event.user, run__status=Run.Status.RUNNING,
                                                 run__graph__active=True).select_related("run__graph")):
                if _holds(doc_of(wait.run.graph).data(wait.node).get("condition"), wait.run):
                    touched += bool(resume(wait))
        for row in list(Start.objects.filter(event=event.name, graph__active=True).select_related("graph")):
            doc = doc_of(row.graph)
            kind = doc.kind(row.node)
            if kind is not None and kind.match is not None and kind.match(doc.data(row.node), row.out, event):
                touched += bool(start(row.graph, row.node, row.out, event.user, _ctx_of(event)))
    finally:
        _depth.reset(token)
    return touched


def start_manual(graph, node_id, user=None):
    """Кнопка автора «Вручную»: запустить для игрока или для мира."""
    kind = doc_of(graph).kind(node_id)
    if kind is None or kind.name != "manual":
        raise ValueError("это не нода «Вручную»")
    return start(graph, node_id, "fire", user, {"event": N.MANUAL_EVENT}, repeat="always")


# ---------- время ----------

def _time_target(data, game):
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
        data = doc_of(row.graph).data(row.node)
        try:
            target = _time_target(data, game)
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
        if _holds(doc_of(wait.run.graph).data(wait.node).get("condition"), wait.run):
            done += bool(resume(wait))
    done += _time_starts()
    return done
