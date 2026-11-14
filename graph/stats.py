"""Что показывает холст: сколько раз прошли через ноду, сколько игроков, кто сейчас ждёт и как давно, итоги прохождений."""
from django.db.models import Count, Min
from django.utils import timezone

from graph.models import Hit, Run, Wait


def of(graph):
    nodes = {}
    for row in Hit.objects.filter(graph=graph).values("node").annotate(hits=Count("id"), players=Count("user", distinct=True)):
        nodes[row["node"]] = {"hits": row["hits"], "players": row["players"], "waiting": 0, "oldest_days": 0.0}
    now = timezone.now()
    for row in Wait.objects.filter(run__graph=graph, run__status=Run.Status.RUNNING).values("node").annotate(n=Count("run", distinct=True), oldest=Min("created_at")):
        slot = nodes.setdefault(row["node"], {"hits": 0, "players": 0, "waiting": 0, "oldest_days": 0.0})
        slot["waiting"] = row["n"]
        slot["oldest_days"] = round((now - row["oldest"]).total_seconds() / 86400, 1)
    runs = Run.objects.filter(graph=graph)
    outcomes = {row["outcome"] or "done": row["n"] for row in runs.filter(status=Run.Status.DONE).values("outcome").annotate(n=Count("id"))}
    return {"nodes": nodes, "running": runs.filter(status=Run.Status.RUNNING).count(), "outcomes": outcomes}


def waiting(graph, node_id, limit=50):
    """Кто ждёт на ноде: (игрок или None, с какого момента)."""
    rows = Wait.objects.filter(run__graph=graph, run__status=Run.Status.RUNNING, node=node_id).select_related("run__user").order_by("created_at")
    seen, out = set(), []
    for wait in rows:
        if wait.run_id in seen:
            continue
        seen.add(wait.run_id)
        out.append((wait.run.user, wait.created_at))
        if len(out) >= limit:
            break
    return out
