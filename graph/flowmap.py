"""Карта сценария для страницы «Мир»: опорные ноды (старты, этапы, ожидания, ветвления) и провода между ними, а поверх — общее
прохождение: что уже пройдено, где сценарий стоит сейчас и чего ждёт. Прохождение одно на весь мир, а не по игроку."""
from collections import defaultdict, deque

from django.db.models import Count, Max
from django.utils import timezone

from graph import nodes as N
from graph import runtime
from graph.models import Branching, Hit, Run, Wait

ALWAYS = {"stage", "wait", "wait_cond", "branching", "branch_head", "end", "scenario_reset", "branch_restart", "crew", "join"}
ROLES = {"stage": "stage", "wait": "wait", "wait_cond": "wait", "branching": "branch", "branch_head": "branch", "end": "end", "scenario_reset": "end",
         "branch_restart": "end"}


def _title(doc, node_id):
    kind = doc.kind(node_id)
    data = doc.data(node_id)
    if kind.name == "stage":
        return str(data.get("title") or "").strip() or "Этап без названия"
    title = N.titled(kind, data)
    if kind.group in N.NOUNS:
        value = next((str(data[k]).strip() for k in ("command", "name", "path", "tag", "text", "subject") if str(data.get(k) or "").strip()), "")
        if value:
            title = f"{title} · {value}"
    return title


def _role(doc, node_id):
    kind = doc.kind(node_id)
    if kind.name in ROLES:
        return ROLES[kind.name]
    if kind.group in N.NOUNS:
        return "start" if doc.is_start(node_id) else "event"
    return "other"


def _milestone(doc, node_id, waiting):
    kind = doc.kind(node_id)
    if kind is None or kind.name in ("note", "frame") or kind.name in N.CONTROLS:
        return False
    return node_id in waiting or kind.name in ALWAYS or kind.group in N.NOUNS


def _edges(doc, kept):
    """Провода потока между опорными нодами: цепочка из неопорных нод схлопывается; ветвление ведёт в «Начало ветки» внутри себя."""
    found = set()
    for node_id in kept:
        seen, queue = {node_id}, deque()
        for (src, _), targets in doc.flow.items():
            if src == node_id:
                queue.extend(dst for dst, _ in targets)
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            if current in kept:
                found.add((node_id, current))
                continue
            for (src, _), targets in doc.flow.items():
                if src == current:
                    queue.extend(dst for dst, _ in targets)
    for node_id in kept:
        if doc.kind(node_id).name == "branch_head":
            parent = node_id.rsplit("/", 1)[0]
            if parent in kept and doc.kind(parent) is not None and doc.kind(parent).name == "branching":
                found.add((parent, node_id))
    return sorted(found)


def _layers(kept, edges):
    """Колонка = самый длинный путь до ноды; обратные провода (циклы сценария) не считаются."""
    out = defaultdict(list)
    for a, b in edges:
        out[a].append(b)
    state, back = {}, set()
    for root in sorted(kept):
        if root in state:
            continue
        stack = [(root, iter(out[root]))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            for nxt in it:
                if state.get(nxt) == 1:
                    back.add((node, nxt))
                elif nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, iter(out[nxt])))
                    break
            else:
                state[node] = 2
                stack.pop()
    ahead = [(a, b) for a, b in edges if (a, b) not in back]
    depth, indeg, nxt = {node: 0 for node in kept}, {node: 0 for node in kept}, defaultdict(list)
    for a, b in ahead:
        indeg[b] += 1
        nxt[a].append(b)
    queue = deque(node for node in kept if not indeg[node])
    while queue:
        node = queue.popleft()
        for follower in nxt[node]:
            depth[follower] = max(depth[follower], depth[node] + 1)
            indeg[follower] -= 1
            if not indeg[follower]:
                queue.append(follower)
    return depth, back


def _rows(doc, kept, depth, edges, back):
    """Строка в колонке: ближе к среднему положению предшественников, при равенстве — как на холсте редактора."""
    before = defaultdict(list)
    for a, b in edges:
        if (a, b) not in back:
            before[b].append(a)
    rows, columns = {}, defaultdict(list)
    for node_id in kept:
        columns[depth[node_id]].append(node_id)
    for col in sorted(columns):
        def key(node_id):
            node = doc.nodes[node_id]
            prior = [rows[p] for p in before[node_id] if p in rows]
            return (sum(prior) / len(prior) if prior else 0, node.get("y") or 0, node.get("x") or 0, node_id)
        for index, node_id in enumerate(sorted(columns[col], key=key)):
            rows[node_id] = index
    return rows


def _owner(run):
    if run.crew_id:
        return f"группа «{run.crew.name}»"
    return run.owner.get_username() if run.owner_id else ""


def _enclosing(branchings, node_id):
    found = [b for b in branchings if node_id.startswith(b + "/")]
    return max(found, key=len) if found else ""


def build(graph):
    """Карта: узлы с колонкой и строкой, провода, живые ожидания и состояние ветвлений."""
    doc = runtime.doc_of(graph)
    now = timezone.now()
    waits = defaultdict(list)
    for wait in Wait.objects.filter(run__graph=graph, run__status=Run.Status.RUNNING).select_related("run__owner", "run__crew").order_by("created_at"):
        if wait.node in doc.nodes:
            waits[wait.node].append(wait)
    hits = {row["node"]: row for row in Hit.objects.filter(graph=graph).values("node").annotate(n=Count("id"), last=Max("at"))}
    kept = {node_id for node_id in doc.nodes if _milestone(doc, node_id, waits)}
    edges = _edges(doc, kept)
    depth, back = _layers(kept, edges)
    rows = _rows(doc, kept, depth, edges, back)
    branchings = [node_id for node_id in doc.nodes if doc.kind(node_id) is not None and doc.kind(node_id).name == "branching"]
    out = []
    for node_id in sorted(kept, key=lambda nid: (depth[nid], rows[nid])):
        seen, here = hits.get(node_id), {}
        for wait in waits.get(node_id, []):
            here.setdefault(wait.run_id, wait)
        out.append({"id": node_id, "kind": doc.kind(node_id).name, "role": _role(doc, node_id), "title": _title(doc, node_id), "col": depth[node_id],
                    "row": rows[node_id], "branch": _enclosing(branchings, node_id), "hits": seen["n"] if seen else 0, "last_at": seen["last"] if seen else None,
                    "here": len(here), "state": "here" if here else "done" if seen else "ahead",
                    "waits": [{"owner": _owner(w.run), "since": w.created_at, "until": w.until, "kind": w.kind} for w in list(here.values())[:6]]})
    return {"nodes": out, "edges": [{"from": a, "to": b, "back": (a, b) in back} for a, b in edges], "cols": max(depth.values(), default=-1) + 1,
            "rows": max(rows.values(), default=-1) + 1, "forks": _forks(graph, doc, branchings, now)}


def _forks(graph, doc, branchings, now):
    """Ветвления: сколько веток занято, свободна ли вакансия, чьи ветки и где они стоят."""
    result = []
    for node_id in branchings:
        data = doc.data(node_id)
        spawn = Branching.objects.filter(graph=graph, node=node_id).first()
        runs = list(Run.objects.filter(graph=graph, state__fork=node_id).select_related("owner", "crew").order_by("-started_at", "-id")[:40])
        stands = {w.run_id: w.node for w in Wait.objects.filter(run__in=[r.pk for r in runs]).order_by("-created_at")}
        branches = []
        for run in runs:
            free = bool((run.state or {}).get("vacancy"))
            at = stands.get(run.pk)
            branches.append({"run": run.pk, "state": "done" if run.status == Run.Status.DONE else "free" if free else "taken", "owner": _owner(run),
                             "at": _title(doc, at) if at in doc.nodes and doc.kind(at) is not None else "", "outcome": run.outcome, "started_at": run.started_at})
        name = str(data.get("name") or "").strip()
        result.append({"node": node_id, "title": name or "Ветвление", "repeat": data.get("repeat") == "yes", "open": True if spawn is None else spawn.open,
                       "taken": spawn.taken if spawn else sum(1 for b in branches if b["state"] == "taken"), "total": _num(data.get("total")), "branches": branches})
    return result


def _num(value):
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def here_titles(graph, limit=3):
    """Названия нод, на которых сценарий стоит прямо сейчас (для карточки в списке)."""
    doc = runtime.doc_of(graph)
    found = []
    for row in Wait.objects.filter(run__graph=graph, run__status=Run.Status.RUNNING).values("node").annotate(n=Count("run", distinct=True)).order_by("-n", "node"):
        if row["node"] in doc.nodes and doc.kind(row["node"]) is not None and doc.kind(row["node"]).name not in ("note", "frame"):
            found.append(_title(doc, row["node"]))
    return list(dict.fromkeys(found))[:limit]
