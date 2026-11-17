"""Возможности: что сценарий предлагает игроку в интерфейсе игры — вариант письма (mail/talk.py), скрытую команду терминала
(terminal/engine/offers.py), окно с выбором и кнопку у файла (desktop).

Что предлагается — нода-сущность «Возможность» (ключ «слаг:нода»). Что игрок видит — «Возможность: Изменить»: Открыть,
Показать «???» (знает, что вариант есть) или Скрыть (по умолчанию). Потоком — инициатору или всем, держится до следующего
изменения; проводом условия во «Когда» — пока условие верно у игрока (побеждает самое открытое), но «Скрыть» потоком его
перекрывает. Верный ответ скрывает возможность вместе с её группой, неверный — ничего (лимит попыток — счётчик сценария). Чем кончилось — событие offer.used («Возможность: Использована»): выходы по каналу
(Верно/Неверно, кнопки окна, «Нажата») и развилки текста.
"""
import contextvars
import re
from dataclasses import dataclass, field

from django.db.models import Q

from graph.models import Graph, Offer, OfferTry, Run

ENTITY = "ent:offer"
OPEN = "act:offer"
RANK = {"hidden": 0, "teaser": 1, "open": 2}
USED = "on:offer.used"
_busy = contextvars.ContextVar("offers_busy", default=frozenset())


def key(graph, node):
    return f"{graph.slug}:{node}"


def parse(text):
    """(граф, нода) из «слаг:нода» или None."""
    slug, _, node = str(text or "").strip().partition(":")
    graph = Graph.objects.filter(slug=slug).first() if slug and node else None
    return (graph, node) if graph is not None else None


def _text(data, name):
    value = data.get(name)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _keys(value):
    return [str(one).strip() for one in (value if isinstance(value, (list, tuple)) else [value]) if str(one or "").strip()]


def spec_of(data):
    """Что предлагает сущность «Возможность» (данные с подставленными проводами)."""
    def many(name):
        value = data.get(name)
        if isinstance(value, str):
            value = value.split(",") if name == "buttons" else [value]
        return [str(one).strip() for one in value or [] if str(one or "").strip()]

    letter = _text(data, "letter")
    mode = data.get("mode") if data.get("mode") in ("new", "reply", "forward") else "new"
    if letter and mode == "new":                    # письмо на входе: «Новое» не бывает
        mode = "reply"
    return {"channel": data.get("channel") or "mail", "mode": mode, "letter": letter,
            "command": _text(data, "command"), "items": many("item"), "path": _text(data, "path"),
            "message": str(data.get("message") or ""), "buttons": many("buttons"),
            "reply_ok": _text(data, "reply_ok"), "reply_wrong": _text(data, "reply_wrong"), "to": [one.lower() for one in many("to")],
            "title": _text(data, "title"), "caption": _text(data, "caption"),
            "text": str(data.get("text") or ""), "attach": many("attach"),
            "group": _text(data, "group")[:64]}


def _state(data):
    """Состояние ноды «Изменить»: open | mystery | hidden."""
    value = (data or {}).get("state")
    return value if value in ("open", "mystery", "hidden") else "open"


# ---- выходы «Использована» -----------------------------------------------------------------------------------------------

FORK = re.compile(r"\[\[(.+?)\]\]", re.DOTALL)
FORK_NAME = re.compile(r"^\s*([^|:\s][^|:]*?):\s+(.*)$", re.DOTALL)


def fork(body):
    """Развилка [[док: 7|9]] -> ("док", ["7", "9"]); без имени — ("", [...]). Имя — до двоеточия с пробелом (12:00 — не имя)."""
    found = FORK_NAME.match(body)
    name, rest = (found.group(1).strip(), found.group(2)) if found else ("", body)
    return name, [option.strip() for option in rest.split("|") if option.strip()]


def forks(text):
    """Выходы развилок текста: [(имя выхода, подпись)] — «fork:док» / «fork:1» («Развилка 1»)."""
    out = []
    for number, found in enumerate(FORK.finditer(text or ""), 1):
        name, _ = fork(found.group(1))
        out.append((f"fork:{name or number}", name or f"Развилка {number}"))
    return out


def fork_values(text, words):
    """Выбранные слова по выходам развилок: {"док": "7", "2": "ночь"} (ключ — имя выхода без «fork:»)."""
    return {name[5:]: word for (name, _), word in zip(forks(text), words)}


def used_outs(data):
    """Выходы «Использована» по данным сущности: [(имя, подпись, тип)] — события, затем развилки (текст)."""
    channel = data.get("channel") or "mail"
    if channel == "choice":
        buttons = spec_of(data)["buttons"]
        events = [(f"b{number}", label, "event") for number, label in enumerate(buttons, 1)]
    elif channel == "file":
        events = [("ok", "Нажата", "event")]
    else:
        events = [("ok", "Верно", "event"), ("wrong", "Неверно", "event")]
    text = str(data.get("text") or "") if channel in ("mail", "command") else ""
    return events + [(name, label, "text") for name, label in forks(text)]


def wired_entity(doc, node_id, slug=""):
    """Сущность «Возможность» ноды (её поле «Возможность»): провод с ноды-сущности или ключ этого графа. Иначе None."""
    src = doc.refs.get((node_id, "offer"))
    if src is not None:
        kind = doc.kind(src[0])
        return src[0] if kind is not None and kind.name == ENTITY else None
    keys = _keys(doc.data(node_id).get("offer"))
    if len(keys) == 1 and slug:
        head, _, node = keys[0].partition(":")
        if head == slug and doc.kind(node) is not None and doc.kind(node).name == ENTITY:
            return node
    return None


def used_iface(doc, node_id, slug=""):
    """Сокеты «Использована» по подключённой сущности: {"outputs", "out_types", "labels"} или None (сущность не известна)."""
    entity = wired_entity(doc, node_id, slug)
    if entity is None:
        return None
    outs = used_outs(doc.data(entity))
    return {"outputs": [name for name, _, _ in outs], "out_types": {name: kind for name, _, kind in outs},
            "labels": {name: label for name, label, _ in outs}}


def match_data(graph, doc, node_id, data):
    """Данные «Использована» для сверки с событием: ключ сущности, если она пришла проводом."""
    src = doc.refs.get((node_id, "offer"))
    if src is not None and doc.kind(src[0]) is not None and doc.kind(src[0]).name == ENTITY:
        return {**data, "offer": key(graph, src[0])}
    return data


# ---- открыть и закрыть ---------------------------------------------------------------------------------------------------

def open_offer(graph, node, spec, user=None, show="open", profile=None):
    """Открыть (снова) игроку, учётке (profile — всем на ней) или всем — или показать закрытой «???» (show="mystery"):
    скрытия игроков снимаются."""
    Offer.objects.filter(graph=graph, node=node, user=user, profile=profile, standing=False).delete()
    Offer.objects.create(graph=graph, node=node, user=user, profile=profile, channel=spec["channel"], group=spec["group"],
                         spec={**spec, "show": show})
    if profile is None:
        tries = OfferTry.objects.filter(graph=graph, node=node)
        (tries if user is None else tries.filter(user=user)).delete()


def close(graph, node, user=None, profile=None):
    """Закрыть учётке (profile — у всех на ней), игроку (возможность «всем» и по условию — только для него) или всем
    (кроме объявленных условием)."""
    if profile is not None:
        Offer.objects.filter(graph=graph, node=node, profile=profile).delete()
        return
    if user is None:
        Offer.objects.filter(graph=graph, node=node, standing=False).delete()
        OfferTry.objects.filter(graph=graph, node=node).delete()
        return
    Offer.objects.filter(graph=graph, node=node, user=user).delete()
    if Offer.objects.filter(graph=graph, node=node, user=None).exists():
        OfferTry.objects.update_or_create(graph=graph, node=node, user=user, defaults={"closed": True})


def close_group(graph, group, user=None, profile=None):
    for node in set(Offer.objects.filter(graph=graph, group=group).values_list("node", flat=True)):
        close(graph, node, user, profile)


def _entities(doc):
    return [node for node in doc.nodes if doc.kind(node) is not None and doc.kind(node).name == ENTITY]


def declared(doc, node_id, slug):
    """Сущности этого графа, которые «Изменить» с условием во «Когда» объявляет: провод с сущности, ключи этого графа или, у
    «Группу», — вся группа (имя текстом или группа поданной возможности)."""
    src = doc.refs.get((node_id, "offer"))
    found, names = [], []
    if src is not None:
        kind = doc.kind(src[0])
        found = [src[0]] if kind is not None and kind.name == ENTITY else []
    else:
        for one in _keys(doc.data(node_id).get("offer")):
            head, sep, node = one.partition(":")
            if not sep:
                names.append(one)
            elif head == slug and doc.kind(node) is not None and doc.kind(node).name == ENTITY:
                found.append(node)
    if doc.data(node_id).get("whole") != "group":
        return found
    groups = ({spec_of(doc.data(node))["group"] for node in found} | set(names)) - {""}
    return list(dict.fromkeys(found + [node for node in _entities(doc) if spec_of(doc.data(node))["group"] in groups]))


def declare(graph, doc):
    """Возможности по условию (провод во «Когда»): выписать при сохранении графа."""
    Offer.objects.filter(graph=graph, standing=True).delete()
    rows = []
    for node_id in doc.nodes:
        if doc.nodes[node_id].get("type") != OPEN or (node_id, "in") not in doc.refs or _state(doc.data(node_id)) == "hidden":
            continue
        for entity in declared(doc, node_id, graph.slug):
            spec = spec_of(doc.data(entity))
            rows.append(Offer(graph=graph, node=entity, standing=True, channel=spec["channel"], group=spec["group"], spec={"by": node_id}))
    Offer.objects.bulk_create(rows)


def entity_spec(run, graph, node):
    """Что предлагает сущность node графа graph сейчас (провода — в прохождении run или, у чужого графа, по игроку). None — нет её."""
    from graph import runtime

    doc = runtime.doc_of(graph)
    kind = doc.kind(node)
    if kind is None or kind.name != ENTITY:
        return None
    if graph.pk != run.graph_id:
        run = Run(graph=graph, user=run.user, ctx=run.ctx, state={})
    return spec_of(runtime.resolved(run, doc, node))


def act(run, node_id, kind, data):
    """Нода «Возможность: Изменить»: открыть, показать «???» или скрыть — одну или всю группу."""
    from graph import runtime

    scope = data.get("scope") or "player"
    user = run.user if scope == "player" else None
    profile = _account(run, data) if scope == "account" else None
    if scope == "player" and user is None:
        runtime._log(run.graph, f"«{kind.label}»: нет инициатора", None)
        return ["fail"]
    if scope == "account" and profile is None:
        runtime._log(run.graph, f"«{kind.label}»: нет учётки (ни провода, ни учётки у события)", run.user)
        return ["fail"]
    state = _state(data)
    wanted = _keys(data.get("offer"))
    if not wanted:
        runtime._log(run.graph, f"«{kind.label}»: не задана возможность", run.user)
        return ["fail"]
    if data.get("whole") == "group":
        found = []
        for one in wanted:
            graph, name, members = _group(run, one)
            if state == "hidden" and name:
                close_group(graph, name, user, profile)
            found += [(graph, node) for node in members]
    else:
        found = [parse(one) for one in wanted]
        if None in found:
            runtime._log(run.graph, f"«{kind.label}»: нет возможности «{', '.join(wanted)}»", run.user)
            return ["fail"]
    for graph, node in found:
        if state == "hidden":
            close(graph, node, user, profile)
            continue
        spec = entity_spec(run, graph, node)
        if spec is None:
            runtime._log(run.graph, f"«{kind.label}»: «{key(graph, node)}» — не нода «Возможность»", run.user)
            return ["fail"]
        open_offer(graph, node, spec, user, state, profile)
    return ["next"]


def _account(run, data):
    """Учётка для «Учётке»: с провода (логин@хост), иначе учётка события."""
    from machines.models import MachineProfile
    from machines.world import edits

    wanted = _text(data, "account")
    if wanted:
        return edits.account(wanted)
    ctx = run.ctx or {}
    if not ctx.get("host") or not ctx.get("login"):
        return None
    return MachineProfile.objects.filter(machine__hostname=ctx["host"], login=ctx["login"]).first()


def _group(run, one):
    """Группа по значению поля: возможность (её группа в её сценарии, она сама — тоже) или имя (в этом сценарии).
    -> (граф, имя группы, сущности группы)."""
    from graph import runtime

    found = parse(one) if ":" in one else None
    spec = entity_spec(run, *found) if found is not None else None
    graph, name = (found[0], spec["group"]) if spec is not None else (run.graph, one[:64])
    if graph.pk != run.graph_id:
        run = Run(graph=graph, user=run.user, ctx=run.ctx, state={})
    doc = runtime.doc_of(graph)
    members = [node for node in _entities(doc) if name and spec_of(runtime.resolved(run, doc, node))["group"] == name]
    if spec is not None and found[1] not in members:
        members.insert(0, found[1])
    return graph, name, members


# ---- что видит игрок -----------------------------------------------------------------------------------------------------

@dataclass
class View:
    graph: Graph
    node: str
    key: str
    spec: dict
    open: bool
    group: str = ""
    extra: dict = field(default_factory=dict)
    profile: object = None                   # открыта для учётки: ответ скрывает её у всех на ней


def _live(graph, node, by, user, host, login):
    """Возможность по условию сейчас: (что предлагает, open | teaser | hidden) или None (сущности уже нет). Верно условие у
    «Открыть» — открыта; верно только у «Показать «???»» — видна закрытой."""
    from graph import runtime

    doc = runtime.doc_of(graph)
    kind = doc.kind(node)
    if kind is None or kind.name != ENTITY:
        return None
    run = Run(graph=graph, user=user, ctx={"host": host, "login": login}, state={})
    shows = {_state(doc.data(one)) for one in by if doc.kind(one) is not None and runtime._truth(runtime.resolved(run, doc, one).get("in"))}
    state = "open" if "open" in shows else "teaser" if "mystery" in shows else "hidden"
    return spec_of(runtime.resolved(run, doc, node)), state


def visible(user, host="", login="", channel="mail", only=None):
    """Возможности канала для игрока: открытые и закрытые «???» (скрытые не попадают). only — (граф, нода): одна."""
    if user is None:
        return []
    from machines.models import MachineProfile

    account = MachineProfile.objects.filter(machine__hostname=host, login=login).first() if host and login else None
    rows = (Offer.objects.filter(graph__active=True).filter(Q(user=user) | Q(user=None, profile=None) | Q(profile=account) if account is not None
                                                           else Q(user=user) | Q(user=None, profile=None)).select_related("graph"))
    if channel:
        rows = rows.filter(channel=channel)
    if only is not None:
        rows = rows.filter(graph=only[0], node=only[1])
    tries = {(t.graph_id, t.node): t for t in OfferTry.objects.filter(user=user, closed=True)}
    places = {}
    for row in sorted(rows, key=lambda r: (r.user_id is None, r.profile_id is None)):     # свои строки, потом учётки — первыми
        places.setdefault((row.graph_id, row.node), []).append(row)
    found = []
    for place, group in places.items():
        own = [row for row in group if row.user_id is not None or row.profile_id is not None]
        everyone = [row for row in group if row.user_id is None and row.profile_id is None and not row.standing]
        standing = [row for row in group if row.standing]
        graph = group[0].graph
        if place in tries and not own:                                      # скрыта игроку потоком: условия её не возвращают
            continue
        spec, best, held = None, "hidden", None
        for row in own[:2] + everyone[:1]:
            state = "teaser" if (row.spec or {}).get("show") == "mystery" else "open"
            if spec is None or RANK[state] > RANK[best]:
                spec, best, held = row.spec, state, row.profile if row.profile_id is not None else None
        if standing and best != "open":
            busy = _busy.get()
            if place not in busy:                                          # условие может ссылаться на саму возможность
                token = _busy.set(busy | {place})
                try:
                    live = _live(graph, place[1], [str((row.spec or {}).get("by") or "") for row in standing], user, host, login)
                finally:
                    _busy.reset(token)
                if live is not None and RANK[live[1]] > RANK[best]:
                    spec, best = live
        if spec is None or best == "hidden":
            continue
        found.append(View(graph, place[1], key(graph, place[1]), spec, best == "open", spec.get("group") or group[0].group, profile=held))
    return found


def state(user, host, login, text):
    """Возможность «слаг:нода» для игрока: View или None (закрыта, скрыта, нет такой)."""
    found = parse(text)
    if found is None:
        return None
    views = visible(user, host, login, channel=None, only=found)
    return views[0] if views else None


def entity_value(run, node_id, out):
    """Выход сущности «Возможность»: её ключ."""
    return key(run.graph, node_id) if out == "offer" else None


def settle(view, user, right):
    """Засчитать ответ: верный закрывает возможность и её группу — для игрока, а у возможности учётки — у всех на ней.
    Возвращает ok или wrong."""
    if not right:
        return "wrong"
    close(view.graph, view.node, user, view.profile)
    if view.group:
        close_group(view.graph, view.group, user, view.profile)
    return "ok"


def used(view, user, result, *, machine=None, login="", outs=None, words=(), **data):
    """Событие «Возможность: Использована»: outs — выходы ноды, по которым идти; развилки — по словам текста варианта."""
    from engine.events import emit

    words = list(words)
    emit("offer.used", user, machine=machine, login=login, offer=view.key, group=view.group, result=result, outs=list(outs or [result]),
         words=words, forks=fork_values(view.spec.get("text", ""), words), **data)


def placement_of(user, host, path):
    from graph import entities

    return entities.placement_key(user, host, path)


def _glob_path(path, pattern):
    import fnmatch

    return not pattern or (fnmatch.fnmatchcase(path, pattern) if any(ch in pattern for ch in "*?[") else path == pattern)


def choices(user, host="", login=""):
    """Окна с выбором, открытые игроку: [View]."""
    return [view for view in visible(user, host, login, "choice") if view.open and view.spec.get("buttons")]


def choose(user, host, login, key, button, machine=None):
    """Игрок нажал кнопку окна: возможность закрывается (с группой), событие идёт по выходу этой кнопки. False — окна уже нет."""
    view = next((one for one in choices(user, host, login) if one.key == key), None)
    if view is None or button not in view.spec["buttons"]:
        return False
    settle(view, user, True)
    used(view, user, "ok", machine=machine, login=login, outs=["ok", f"b{view.spec['buttons'].index(button) + 1}"], text=button)
    return True


def file_actions(user, host, login, path, item_slug=""):
    """Кнопки у файла path игрока: [View]."""
    found = []
    for view in visible(user, host, login, "file"):
        spec = view.spec
        if not view.open or (spec.get("items") and item_slug not in spec["items"]) or not _glob_path(path, spec.get("path", "")):
            continue
        found.append(view)
    return found


def act_on_file(user, host, login, key, path, item_slug="", machine=None):
    """Игрок нажал кнопку в окне файла: возможность закрывается (с группой), событие с размещением файла."""
    view = next((one for one in file_actions(user, host, login, path, item_slug) if one.key == key), None)
    if view is None:
        return False
    settle(view, user, True)
    used(view, user, "ok", machine=machine, login=login, text=view.spec.get("title", ""), placement=placement_of(user, host, path), item=item_slug)
    return True
