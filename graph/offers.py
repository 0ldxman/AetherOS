"""Возможности: что сценарий открыл игроку в интерфейсе игры. Сейчас канал один — письмо (варианты ответа, mail/talk.py).

Возможность — нода «Возможность: Открыть» графа (ключ «слаг:нода»). Открывает её поток (игроку хода или всем) или провод
условия во вход «Когда» — тогда она объявлена, пока сценарий включён, и открыта тем, у кого условие верно.
Закрывает «Возможность: Закрыть» (возможность или группу) и верный ответ: использованная закрывается вместе со своей группой.
Неверный ответ тратит попытку; кончились — закрыта. Чем кончилось — событие offer.used («Возможность: Использована»).
"""
import contextvars
from dataclasses import dataclass, field

from django.db.models import Q

from graph.models import Graph, Offer, OfferTry, Run

OPEN = "act:offer.open"
ATTACH = ("item", "key", "signed")
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


def _int(value):
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def spec_of(data):
    """Что предлагает нода «Открыть» (данные с подставленными проводами)."""
    characters = data.get("character")
    characters = [str(c).strip() for c in (characters if isinstance(characters, (list, tuple)) else [characters]) if str(c or "").strip()]
    attach = data.get("attach") if data.get("attach") in ATTACH else ""
    condition = data.get("condition")

    def many(name):
        value = data.get(name)
        if isinstance(value, str):
            value = value.split(",") if name == "buttons" else [value]
        return [str(one).strip() for one in value or [] if str(one or "").strip()]

    return {"channel": data.get("channel") or "mail", "mode": data.get("mode") or "reply",
            "command": _text(data, "command"), "machines": [m.lower() for m in many("machine")], "items": many("item"), "path": _text(data, "path"),
            "message": str(data.get("message") or ""), "buttons": many("buttons"),
            "reply_ok": _text(data, "reply_ok"), "reply_wrong": _text(data, "reply_wrong"), "characters": characters, "address": _text(data, "address").lower(),
            "reply_to": _text(data, "reply_to"), "forward_of": _text(data, "forward_of"), "title": _text(data, "title"), "caption": _text(data, "caption"),
            "text": str(data.get("text") or ""), "attach": attach, "attach_item": _text(data, "attach_item") if attach else "",
            "attempts": _int(data.get("attempts")), "account": _text(data, "account").lower(),
            "show": "mystery" if data.get("show") == "mystery" else "open", "closed": "hidden" if data.get("closed") == "hidden" else "mystery",
            "live": condition not in (None, "") and not (isinstance(condition, str) and not condition.strip())}


def _group(data):
    return _text(data, "group")[:64]


# ---- открыть и закрыть ---------------------------------------------------------------------------------------------------

def open_offer(graph, node, data, user=None):
    """Открыть (снова) игроку или всем: попытки сначала, закрытия игроков снимаются."""
    Offer.objects.filter(graph=graph, node=node, user=user, standing=False).delete()
    Offer.objects.create(graph=graph, node=node, user=user, channel=data.get("channel") or "mail", group=_group(data), spec=spec_of(data))
    tries = OfferTry.objects.filter(graph=graph, node=node)
    (tries if user is None else tries.filter(user=user)).delete()


def close(graph, node, user=None):
    """Закрыть игроку (возможность «всем» и по условию — только для него) или всем (кроме объявленных условием)."""
    if user is None:
        Offer.objects.filter(graph=graph, node=node, standing=False).delete()
        OfferTry.objects.filter(graph=graph, node=node).delete()
        return
    Offer.objects.filter(graph=graph, node=node, user=user).delete()
    if Offer.objects.filter(graph=graph, node=node, user=None).exists():
        OfferTry.objects.update_or_create(graph=graph, node=node, user=user, defaults={"closed": True})


def close_group(graph, group, user=None):
    for node in set(Offer.objects.filter(graph=graph, group=group).values_list("node", flat=True)):
        close(graph, node, user)


def declare(graph, doc):
    """Возможности по условию (провод во «Когда»): выписать при сохранении графа."""
    Offer.objects.filter(graph=graph, standing=True).delete()
    rows = [Offer(graph=graph, node=node_id, standing=True, channel=doc.data(node_id).get("channel") or "mail", group=_group(doc.data(node_id)))
            for node_id in doc.nodes if doc.nodes[node_id].get("type") == OPEN and (node_id, "in") in doc.refs]
    Offer.objects.bulk_create(rows)


def act(run, node_id, kind, data):
    """Ноды «Возможность: Открыть» и «Возможность: Закрыть»."""
    from graph import runtime

    user = None if data.get("scope") == "all" else run.user
    if data.get("scope") != "all" and user is None:
        runtime._log(run.graph, f"«{kind.label}»: нет игрока хода", None)
        return ["fail"]
    if kind.name == OPEN:
        open_offer(run.graph, node_id, data, user)
        return ["next"]
    if data.get("variant") == "group":
        group = _text(data, "group")
        if not group:
            runtime._log(run.graph, f"«{kind.label}»: не задана группа", run.user)
            return ["fail"]
        close_group(run.graph, group, user)
        return ["next"]
    wanted = data.get("offer")
    found = [parse(one) for one in (wanted if isinstance(wanted, (list, tuple)) else [wanted]) if str(one or "").strip()]
    if not found or None in found:
        runtime._log(run.graph, f"«{kind.label}»: нет возможности «{wanted}»", run.user)
        return ["fail"]
    for graph, node in found:
        close(graph, node, user)
    return ["next"]


# ---- что видит игрок -----------------------------------------------------------------------------------------------------

@dataclass
class View:
    graph: Graph
    node: str
    key: str
    spec: dict
    open: bool
    group: str = ""
    left: int | None = None           # сколько попыток осталось; None — без ограничения
    extra: dict = field(default_factory=dict)


def _live(row, user, host, login):
    """Данные ноды «Открыть» для игрока сейчас: условие и поля с проводов (без подробностей события — факты игрока)."""
    from graph import runtime

    doc = runtime.doc_of(row.graph)
    if doc.kind(row.node) is None:
        return None
    run = Run(graph=row.graph, user=user, ctx={"host": host, "login": login}, state={})
    return run, runtime.resolved(run, doc, row.node)


def visible(user, host="", login="", channel="mail", only=None):
    """Возможности канала для игрока: открытые и закрытые «???» (скрытые не попадают). only — (граф, нода): одна."""
    from graph import runtime

    if user is None:
        return []
    rows = Offer.objects.filter(graph__active=True).filter(Q(user=user) | Q(user=None)).select_related("graph")
    if channel:
        rows = rows.filter(channel=channel)
    if only is not None:
        rows = rows.filter(graph=only[0], node=only[1])
    tries = {(t.graph_id, t.node): t for t in OfferTry.objects.filter(user=user)}
    account = f"{login}@{host}".lower()
    seen = {}
    for row in sorted(rows, key=lambda r: r.user_id is None):           # своя строка важнее строки «всем»
        place = (row.graph_id, row.node)
        if place in seen:
            continue
        seen[place] = None
        done = tries.get(place)
        if done is not None and done.closed and (row.user_id is None or row.standing):
            continue
        busy = _busy.get()
        if place in busy:                                                  # условие ссылается на саму возможность
            continue
        token = _busy.set(busy | {place})
        try:
            spec, is_open = row.spec, True
            if row.standing or (row.spec or {}).get("live"):
                live = _live(row, user, host, login)
                if live is None:
                    continue
                run, data = live
                if row.standing:
                    spec, is_open = spec_of(data), runtime._truth(data.get("in"))
                if spec.get("live"):
                    is_open = is_open and runtime._holds(data.get("condition"), run)
            is_open = is_open and spec.get("show") != "mystery"
        finally:
            _busy.reset(token)
        attempts, used = spec.get("attempts") or 0, done.used if done is not None else 0
        if attempts and used >= attempts:
            continue
        if spec.get("account") and spec["account"] != account:
            is_open = False
        if not is_open and spec.get("closed") == "hidden":
            continue
        seen[place] = View(row.graph, row.node, key(row.graph, row.node), spec, is_open, row.group, attempts - used if attempts else None)
    return [view for view in seen.values() if view is not None]


def state(user, host, login, text):
    """Возможность «слаг:нода» для игрока: View или None (закрыта, скрыта, нет такой)."""
    found = parse(text)
    if found is None:
        return None
    views = visible(user, host, login, channel=None, only=found)
    return views[0] if views else None


def used(view, user, result, *, machine=None, login="", left=None, words=(), **data):
    """Событие «Возможность: Использована»."""
    from engine.events import emit

    words = list(words)
    emit("offer.used", user, machine=machine, login=login, offer=view.key, group=view.group, result=result, words=words,
         word=words[0] if words else "", left=-1 if left is None else left, **data)


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
    """Игрок нажал кнопку окна: возможность закрывается (с группой), событие с выбранным словом. False — окна уже нет."""
    view = next((one for one in choices(user, host, login) if one.key == key), None)
    if view is None or button not in view.spec["buttons"]:
        return False
    attempt(view, user, True)
    used(view, user, "ok", machine=machine, login=login, words=[button], text=button)
    return True


def file_actions(user, host, login, path, item_slug=""):
    """Действия над файлом path игрока: [View] (кнопки в окне файла)."""
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
    attempt(view, user, True)
    used(view, user, "ok", machine=machine, login=login, text=view.spec.get("title", ""), placement=placement_of(user, host, path), item=item_slug)
    return True


def attempt(view, user, right):
    """Засчитать ответ: верный закрывает возможность и её группу для игрока; неверный тратит попытку.
    Возвращает (ok | wrong | exhausted, сколько попыток осталось или None)."""
    if right:
        close(view.graph, view.node, user)
        if view.group:
            close_group(view.graph, view.group, user)
        return "ok", view.left
    done, _ = OfferTry.objects.get_or_create(graph=view.graph, node=view.node, user=user)
    done.used += 1
    attempts = view.spec.get("attempts") or 0
    if attempts and done.used >= attempts:
        done.closed = True
        done.save(update_fields=["used", "closed"])
        Offer.objects.filter(graph=view.graph, node=view.node, user=user).delete()
        return "exhausted", 0
    done.save(update_fields=["used"])
    return "wrong", attempts - done.used if attempts else None
