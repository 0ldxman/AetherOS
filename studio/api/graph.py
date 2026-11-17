"""Сценарии-графы (приложение graph) для Студии: каталог нод, список, документ графа с проверкой и живыми счётчиками,
кто ждёт на ноде, запуск «Вручную». Раздел прав «Мир»."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from graph import check, nodes, runtime, stats
from graph.models import Graph

router = Router(tags=["graph"])


class GrOption(Schema):
    value: str
    label: str


class GrField(Schema):
    name: str
    label: str
    kind: str
    placeholder: str
    required: bool
    options: list[GrOption]
    socket: str


class GrSock(Schema):
    name: str
    label: str
    type: str = "event"


class GrMany(Schema):
    side: str
    field: str
    prefix: str
    label: str


class GrGrow(Schema):
    field: str
    prefix: str
    type: str
    named: bool
    min: int
    single: list[str]
    needs: str = ""


class GrWhen(Schema):
    field: str
    mode: str
    values: list[str]


class GrInferTo(Schema):
    value: str
    field: str


class GrInfer(Schema):
    mode: str
    by: dict[str, GrInferTo]


class GrPlural(Schema):
    mode: str
    values: list[str]


class GrInline(Schema):
    switch: str
    drop: list[str] = []


class GrKind(Schema):
    name: str
    label: str
    group: str
    subgroup: str
    summary: str
    fields: list[GrField]
    ins: list[str]
    in_types: dict[str, str] = {}
    outs: list[GrSock]
    many: list[GrMany]
    tail: list[GrSock]
    ref: str
    start_only: bool
    help: str
    title: str = ""
    grow: GrGrow | None = None
    when: list[GrWhen] = []
    hidden: bool = False
    owned: str = ""
    typed: str = ""
    covers: dict[str, list[str]] = {}
    follows: dict[str, str] = {}
    plural: dict[str, GrPlural] = {}
    outs_when: dict[str, GrPlural] = {}
    types_from: list[str] = []
    titled: dict[str, str] = {}
    infers: dict[str, GrInfer] = {}
    inline: dict[str, GrInline] = {}


class GrGroup(Schema):
    name: str
    label: str


class GrCatalog(Schema):
    groups: list[GrGroup]
    kinds: list[GrKind]
    start_fields: list[GrField]
    wait_fields: list[GrField]
    types: list[str]
    socket_help: dict[str, str]


class GrIface(Schema):
    inputs: list[GrSock]
    outputs: list[GrSock]


class GrRow(Schema):
    id: int
    slug: str
    title: str
    active: bool
    iface: GrIface
    nodes: int
    running: int
    errors: int
    updated_at: dt.datetime


class GrProblem(Schema):
    node: str
    text: str
    level: str


class GrNodeStat(Schema):
    hits: int
    players: int
    waiting: int
    oldest_days: float


class GrStats(Schema):
    nodes: dict[str, GrNodeStat]
    running: int
    outcomes: dict[str, int]


class GrDetail(Schema):
    id: int
    slug: str
    title: str
    note: str
    active: bool
    owner: str = ""
    doc: dict
    problems: list[GrProblem]
    stats: GrStats
    updated_at: dt.datetime


class GrIn(Schema):
    slug: str
    title: str
    note: str = ""
    active: bool = False
    doc: dict = {}


class GrStartIn(Schema):
    node: str
    player: int | None = None


class GrStarted(Schema):
    status: str
    outcome: str


class GrOwned(Schema):
    id: int | None
    owner: str
    iface: GrIface


class GrWaiter(Schema):
    player: str
    player_id: int | None
    since: dt.datetime


def _iface(doc):
    """«Вход» и «Выход» сценария с подписями: сокеты ноды «Сценарий» в других графах."""
    def socks(kind):
        for node in (doc or {}).get("nodes") or []:
            if isinstance(node, dict) and node.get("type") == kind:
                types = nodes.socket_types(node.get("data"))
                return [GrSock(name=name, label=label, type=types.get(name, "event")) for name, label in nodes.named(node.get("data"))]
        return []
    return GrIface(inputs=socks("group_in"), outputs=socks("group_out"))


def _detail(graph):
    return GrDetail(id=graph.pk, slug=graph.slug, title=graph.title, note=graph.note, active=graph.active, owner=graph.owner,
                    doc=graph.doc or {"nodes": [], "wires": []}, problems=check.problems(graph.doc, graph.slug, graph.owner), stats=stats.of(graph),
                    updated_at=graph.updated_at)


def _apply(graph, body):
    from world import state

    try:
        graph.slug = state.check_name(body.slug)
    except state.WorldError as error:
        raise HttpError(400, str(error)) from None
    if Graph.objects.filter(slug=graph.slug).exclude(pk=graph.pk).exists():
        raise HttpError(400, "Сценарий с таким именем уже есть.")
    if not body.title.strip():
        raise HttpError(400, "Нужно название.")
    try:
        doc = check.clean(body.doc or {"nodes": [], "wires": []})
    except (ValueError, TypeError) as error:
        raise HttpError(400, f"Граф: {error}") from None
    graph.title, graph.note, graph.active, graph.doc = body.title.strip()[:120], body.note, body.active, doc
    graph.save()
    runtime.rebuild_starts(graph)


@router.get("/catalog", response=GrCatalog)
def catalog(request):
    return nodes.catalog()


class GrCheckIn(Schema):
    doc: dict
    slug: str = ""


@router.post("/check", response=list[GrProblem])
def check_doc(request, body: GrCheckIn):
    """Проверка черновика на лету (ничего не сохраняет)."""
    try:
        owner = Graph.objects.filter(slug=body.slug).values_list("owner", flat=True).first() or ""
        return check.problems(check.clean(body.doc), body.slug, owner)
    except (ValueError, TypeError) as error:
        return [GrProblem(node="", text=str(error), level=check.ERROR)]


@router.get("", response=list[GrRow])
def graph_list(request):
    out = []
    for graph in Graph.objects.filter(owner=""):
        found = check.problems(graph.doc, graph.slug)
        out.append(GrRow(id=graph.pk, slug=graph.slug, title=graph.title, active=graph.active, iface=_iface(graph.doc), nodes=len((graph.doc or {}).get("nodes") or []),
                         running=graph.runs.filter(status="running").count(), errors=sum(1 for p in found if p["level"] == check.ERROR),
                         updated_at=graph.updated_at))
    return out


@router.post("", response=GrDetail)
def create(request, body: GrIn):
    graph = Graph()
    _apply(graph, body)
    return _detail(graph)


@router.get("/owned", response=GrOwned)
def owned_graph(request, kind: str, key: str, create: bool = False):
    """Граф попытки у вещи (машина по хосту…): номер и свои выходы; create — завести, если его ещё нет."""
    from graph import owned

    owner = owned.owner_of(kind, key)
    if owner is None:
        raise HttpError(404, "Нет такой вещи.")
    graph = owned.ensure(kind, key) if create else owned.find(owner)
    return GrOwned(id=graph.pk if graph else None, owner=owner, iface=_iface(graph.doc) if graph else GrIface(inputs=[], outputs=[]))


@router.get("/{int:graph_id}", response=GrDetail)
def detail(request, graph_id: int):
    return _detail(get_object_or_404(Graph, pk=graph_id))


@router.put("/{int:graph_id}", response=GrDetail)
def update(request, graph_id: int, body: GrIn):
    graph = get_object_or_404(Graph, pk=graph_id)
    _apply(graph, body)
    return _detail(graph)


@router.delete("/{int:graph_id}", response={204: None})
def delete(request, graph_id: int):
    get_object_or_404(Graph, pk=graph_id).delete()
    return 204, None


@router.get("/{int:graph_id}/stats", response=GrStats)
def graph_stats(request, graph_id: int):
    return stats.of(get_object_or_404(Graph, pk=graph_id))


@router.get("/{int:graph_id}/waiting/{node}", response=list[GrWaiter])
def waiting(request, graph_id: int, node: str):
    graph = get_object_or_404(Graph, pk=graph_id)
    return [GrWaiter(player=user.get_username() if user else "мир", player_id=user.pk if user else None, since=since)
            for user, since in stats.waiting(graph, node)]


@router.post("/{int:graph_id}/start", response=GrStarted)
def manual(request, graph_id: int, body: GrStartIn):
    graph = get_object_or_404(Graph, pk=graph_id)
    user = get_object_or_404(get_user_model(), pk=body.player) if body.player else None
    try:
        run = runtime.start_manual(graph, body.node, user, author=request.user)
    except ValueError as error:
        raise HttpError(400, str(error)) from None
    return GrStarted(status=run.status if run else "skipped", outcome=run.outcome if run else "")
