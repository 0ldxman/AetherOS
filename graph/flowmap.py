"""Карта сценария для страницы «Мир»: граф слева направо. Узлы — «Этапы», «Ветвления» и стартовые события; всё остальное (ожидания, условия,
действия) схлопнуто в стрелки, а то, чего сценарий ждёт прямо сейчас, подписано на стрелке. «Ветвление» — узел, от которого вниз идёт дорожка
с картой потока внутри ветки. Прохождение общее для всего мира: ни одного игрока по отдельности здесь нет, только потоки и их владельцы."""
from collections import defaultdict, deque

from django.db.models import Count, Max

from graph import nodes as N
from graph import runtime
from graph.models import Branching, Hit, Run, Wait
from machines.world import chrono

ROUTERS = {"check", "random", "turns"}
WAITERS = {"wait", "wait_cond"}
VALUE_KEYS = ("command", "name", "path", "tag", "text", "subject", "condition")


def _value(doc, node_id):
    data = doc.data(node_id)
    return next((str(data[k]).strip() for k in VALUE_KEYS if str(data.get(k) or "").strip()), "")


def _title(doc, node_id):
    kind = doc.kind(node_id)
    data = doc.data(node_id)
    if kind.name == "stage":
        return str(data.get("title") or "").strip() or "Этап без названия"
    if kind.name == "branching":
        return str(data.get("name") or "").strip() or "Ветвление"
    if kind.name in N.CONTROLS and str(data.get("name") or "").strip():
        return str(data["name"]).strip()
    title = N.titled(kind, data)
    value = _value(doc, node_id) if (kind.group in N.NOUNS or kind.name in ROUTERS) else ""
    return f"{title} · {value}" if value else title


def _what(doc, node_id):
    """Коротко, чего ждёт нода: «vault» у команды, «условие», время у «Ждать»."""
    kind = doc.kind(node_id)
    if kind.name == "wait_cond":
        return "условие"
    if kind.name == "wait":
        return ""
    return _value(doc, node_id) or N.titled(kind, doc.data(node_id))


def _out_label(kind, out):
    for sock in (*kind.outs, *kind.tail):
        if sock.name == out:
            return sock.label
    for many in kind.many:
        if many.side == "out" and many.prefix and out.startswith(many.prefix):
            return str(getattr(many, "label", "") or "").replace("{n}", out[len(many.prefix):]) or out
    return ""


def _iso(value):
    return value.isoformat() if value else None


def _game(value):
    """Реальный момент как игровое время «ГГГГ-ММ-ДД ЧЧ:ММ»."""
    return chrono.stamp(value) if value else None


def _owner(run):
    if run.crew_id:
        return f"группа «{run.crew.name}»"
    return run.owner.get_username() if run.owner_id else ""


def _layers(kept, edges):
    """Колонка = самый длинный путь до узла; обратные провода (циклы сценария) отделяются."""
    out = defaultdict(list)
    for a, b in edges:
        out[a].append(b)
    state, back = {}, set()
    for root in sorted(kept):
        if root in state:
            continue
        stack = [(root, iter(sorted(out[root])))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            for nxt in it:
                if state.get(nxt) == 1:
                    back.add((node, nxt))
                elif nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, iter(sorted(out[nxt]))))
                    break
            else:
                state[node] = 2
                stack.pop()
    depth, indeg, follow = {node: 0 for node in kept}, {node: 0 for node in kept}, defaultdict(list)
    for a, b in edges:
        if (a, b) not in back:
            indeg[b] += 1
            follow[a].append(b)
    queue = deque(node for node in kept if not indeg[node])
    while queue:
        node = queue.popleft()
        for nxt in follow[node]:
            depth[nxt] = max(depth[nxt], depth[node] + 1)
            indeg[nxt] -= 1
            if not indeg[nxt]:
                queue.append(nxt)
    return depth, back


def build(graph):
    doc = runtime.doc_of(graph)
    kinds = defaultdict(lambda: None, {nid: doc.kind(nid) for nid in doc.nodes})
    waits = defaultdict(list)
    for wait in Wait.objects.filter(run__graph=graph, run__status=Run.Status.RUNNING).select_related("run__owner", "run__crew").order_by("created_at"):
        if wait.node in doc.nodes:
            waits[wait.node].append(wait)
    hits = {row["node"]: row for row in Hit.objects.filter(graph=graph).values("node").annotate(n=Count("id"), last=Max("at"))}

    def is_kind(nid, *names):
        return kinds[nid] is not None and kinds[nid].name in names

    forks = [nid for nid in doc.nodes if is_kind(nid, "branching")]
    heads = {nid.rsplit("/", 1)[0]: nid for nid in doc.nodes if is_kind(nid, "branch_head")}              # «Ветвление» → его «Начало ветки»
    visible = {nid for nid in doc.nodes if is_kind(nid, "stage", "branching")}
    for nid in doc.nodes:                                                                                 # стартовые события и кнопки пульта с проводом дальше
        if kinds[nid] is not None and kinds[nid].group in N.NOUNS and doc.is_start(nid) and doc.wired(nid):
            visible.add(nid)
    if not any(is_kind(nid, "stage", "branching") for nid in doc.nodes):                                  # этапов нет: ожидания и события становятся узлами
        visible |= {nid for nid in doc.nodes if is_kind(nid, *WAITERS) or (kinds[nid] is not None and kinds[nid].group in N.NOUNS and nid in doc.fed)}

    by_src = defaultdict(list)
    for (src, out), targets in doc.flow.items():
        by_src[src] += [(out, dst) for dst, _ in targets]

    def wait_info(chain):
        """Чего ждут на скрытых нодах цепочки: {count, items: [{kind, what, until}], waits: [...]} или None."""
        found = [(h, w) for h in chain for w in waits.get(h, [])]
        if not found:
            return None
        runs, items, rows = set(), {}, []
        for h, w in found:
            runs.add(w.run_id)
            items.setdefault((w.kind, _what(doc, h), _iso(w.until) if w.kind == "time" else None),
                          {"kind": w.kind, "what": _what(doc, h), "until": _iso(w.until), "until_game": _game(w.until)})
            if len(rows) < 6:
                rows.append({"id": w.pk, "run": w.run_id, "owner": _owner(w.run), "since": _iso(w.created_at), "since_game": _game(w.created_at), "until": _iso(w.until), "until_game": _game(w.until), "kind": w.kind, "what": _what(doc, h), "free": bool((w.run.state or {}).get("vacancy"))})
        return {"count": len(runs), "items": list(items.values())[:3], "more": max(0, len(items) - 3), "waits": rows}

    edges, tails, stubs = {}, {}, {}
    for a in list(visible):
        queue = deque((dst, "", (), False) for _, dst in by_src[a])
        if a in heads and heads[a] in doc.nodes:                                                          # «Ветвление» ведёт вниз, в карту потока ветки
            queue.extend((dst, "", (heads[a],), True) for _, dst in by_src[heads[a]])
        seen, dead, lane_seen = {a}, [], []
        while queue:
            cur, label, via, lane = queue.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            if cur in visible:
                edges.setdefault((a, cur), {"label": label, "via": via, "lane": lane})
                continue
            chain = via + (cur,)
            outs = by_src[cur]
            if lane:
                lane_seen.append(cur)
            if not outs:
                dead.append((chain, lane))
            for out, dst in outs:
                queue.append((dst, _out_label(kinds[cur], out) if is_kind(cur, *ROUTERS) else label, chain, lane))
        tail = wait_info([h for chain, in_lane in dead if not in_lane for h in chain if h in waits])
        if tail:
            tails[a] = tail
        if a in heads and not any(src == a and info["lane"] for (src, _), info in edges.items()):         # в ветке нет этапов: дорожка-заглушка
            stubs[a] = (heads[a], *lane_seen)
    for a, via in stubs.items():
        visible.add(a + "#lane")
        edges[(a, a + "#lane")] = {"label": "", "via": via, "lane": True}

    depth, back = _layers(visible, set(edges))

    def enclosing(nid):
        found = [f for f in forks if nid.startswith(f + "/")]
        return max(found, key=len) if found else ""

    def order(nid):
        node = doc.nodes[nid[:-5] if nid.endswith("#lane") else nid]
        return (node.get("y") or 0, node.get("x") or 0, nid)

    branch = {nid: (nid[:-5] if nid.endswith("#lane") else enclosing(nid)) for nid in visible}
    preds = defaultdict(list)
    for a, b in edges:
        if (a, b) not in back:
            preds[b].append(a)
    row, start = {}, 0
    groups = sorted({*branch.values()}, key=lambda g: (-1, 0) if g == "" else (depth.get(g, 0), order(g)))
    for group in groups:
        members = [n for n in visible if branch[n] == group]
        taken = defaultdict(set)
        for nid in sorted(members, key=lambda n: (depth[n], order(n))):
            near = [row[p] - start for p in preds[nid] if p in row and branch[p] == group]
            want = round(sum(near) / len(near)) if near else 0
            while want in taken[depth[nid]]:
                want += 1
            taken[depth[nid]].add(want)
            row[nid] = start + want
        start = max(row[n] for n in members) + 1 if members else start

    out_edges = defaultdict(list)
    for (a, b), info in edges.items():
        if not info["lane"]:                                                                              # ожидание свободной ветки не делает ветвление «стоящим»
            out_edges[a].append(wait_info(info["via"]))
    nodes_out = []
    for nid in sorted(visible, key=lambda n: (depth[n], row[n])):
        seen = hits.get(nid)
        ringing = tails.get(nid) or next((w for w in out_edges[nid] if w), None)
        if nid.endswith("#lane"):
            nodes_out.append({"id": nid, "title": "В ветке нет этапов", "hint": "", "role": "lane", "col": depth[nid], "row": row[nid], "branch": branch[nid], "state": "ahead", "hits": 0, "last_at": None, "here": False})
            continue
        role = "fork" if is_kind(nid, "branching") else "stage" if is_kind(nid, "stage") else "start"
        full = _title(doc, nid)
        nodes_out.append({"id": nid, "title": (_value(doc, nid) or full) if role == "start" else full, "hint": full if role == "start" else "", "role": role, "col": depth[nid], "row": row[nid], "branch": branch[nid],
                          "state": "done" if seen else "ahead", "hits": seen["n"] if seen else 0, "last_at": _iso(seen["last"]) if seen else None, "here": bool(ringing)})
    edges_out = [{"src": a, "to": b, "label": info["label"], "lane": info["lane"], "back": (a, b) in back, "wait": wait_info(info["via"])} for (a, b), info in sorted(edges.items())]
    return {"nodes": nodes_out, "edges": edges_out, "tails": [{"node": a, **info} for a, info in tails.items()], "cols": max(depth.values(), default=-1) + 1,
            "rows": max(row.values(), default=-1) + 1, "forks": _forks(graph, doc, forks, visible, edges, waits), "here": len({w.run_id for ws in waits.values() for w in ws})}


def _forks(graph, doc, forks, visible, edges, waits):
    """Ветвления: сколько веток занято, набор открыт ли, и каждая ветка: чья, где стоит, идёт или закончена."""
    spawns = {b.node: b for b in Branching.objects.filter(graph=graph)}
    result = []
    for nid in forks:
        if nid not in visible:
            continue
        data, spawn = doc.data(nid), spawns.get(nid)
        runs = list(Run.objects.filter(graph=graph, state__fork=nid).select_related("owner", "crew").order_by("-started_at", "-id")[:60])
        stands = {}
        for wait in Wait.objects.filter(run__in=[r.pk for r in runs]).order_by("-created_at"):
            stands.setdefault(wait.run_id, wait.node)
        branches = []
        for run in runs:
            at = stands.get(run.pk)
            branches.append({"run": run.pk, "state": "done" if run.status == Run.Status.DONE else "free" if (run.state or {}).get("vacancy") else "taken", "owner": _owner(run),
                             "at": (_what(doc, at) or _title(doc, at)) if at in doc.nodes and doc.kind(at) is not None else "", "outcome": run.outcome})
        try:
            total = max(0, int(float(data.get("total"))))
        except (TypeError, ValueError):
            total = 0
        result.append({"node": nid, "title": _title(doc, nid), "repeat": data.get("repeat") == "yes", "open": True if spawn is None else spawn.open,
                       "taken": spawn.taken if spawn else sum(1 for b in branches if b["state"] == "taken"), "total": total,
                       "done": sum(1 for b in branches if b["state"] == "done" and b["outcome"] not in ("cancelled", "restarted", "stopped")), "branches": branches})
    return result


def here_titles(graph, limit=3):
    """Названия нод, на которых сценарий стоит прямо сейчас (для карточки в списке)."""
    doc = runtime.doc_of(graph)
    found = []
    for row in Wait.objects.filter(run__graph=graph, run__status=Run.Status.RUNNING).values("node").annotate(n=Count("run", distinct=True)).order_by("-n", "node"):
        if row["node"] in doc.nodes and doc.kind(row["node"]) is not None and doc.kind(row["node"]).name not in ("note", "frame"):
            found.append(_title(doc, row["node"]))
    return list(dict.fromkeys(found))[:limit]
