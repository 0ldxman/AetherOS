"""Сценарии-графы (приложение graph) для Студии: каталог нод, список, документ графа с проверкой и живыми счётчиками,
кто ждёт на ноде, запуск «Вручную». Раздел прав «Мир»."""
import datetime as dt
from typing import Any

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from graph import check, flowmap, journal, nodes, runtime, stats
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


class GrRowOp(Schema):
    value: str
    label: str


class GrGrow(Schema):
    field: str
    prefix: str
    type: str
    named: bool
    min: int
    single: list[str]
    needs: str = ""
    ops: list[GrRowOp] = []
    mode: str = ""
    valueless: list[str] = []
    rowless: list[str] = []
    value: bool = True
    outs: bool = False


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
    family: str = ""
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
    wait_skip: list[str] = []
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
    value: Any = None                           # значение управления: да/нет, текст, вариант, число (у кнопки пусто)


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


@router.post("/{int:graph_id}/control", response=GrStarted)
def control(request, graph_id: int, body: GrStartIn):
    graph = get_object_or_404(Graph, pk=graph_id)
    user = get_object_or_404(get_user_model(), pk=body.player) if body.player else None
    try:
        run = runtime.start_control(graph, body.node, body.value, user, author=request.user)
    except ValueError as error:
        raise HttpError(400, str(error)) from None
    return GrStarted(status=run.status if run else "skipped", outcome=run.outcome if run else "")


# ---------- страница «Мир»: карточки сценариев, страница сценария (карта, пульт, журнал) ----------

class PnCard(Schema):
    id: int
    slug: str
    title: str
    active: bool
    errors: int
    running: int
    waiting: int
    here: list[str]                              # где сценарий стоит сейчас: названия нод с ожиданиями


class PnFlow(Schema):
    # граф слева направо: узлы (col, row), стрелки с подписью ожидания, дорожки ветвлений; разбор — graph/flowmap.py
    nodes: list[Any]
    edges: list[Any]
    tails: list[Any]
    forks: list[Any]
    cols: int
    rows: int
    here: int                                    # сколько потоков стоят на ожиданиях


class PnControl(Schema):
    node: str
    kind: str                                    # manual | ctl_switch | ctl_text | ctl_choice | ctl_number
    name: str
    value: Any = None
    options: list[str] = []
    min: float | None = None
    max: float | None = None
    step: float | None = None


class PnTile(Schema):
    key: str                                     # node или «title:N»
    w: int                                       # ширина в двенадцатых долях строки: 3, 4, 6 или 12
    title: str = ""                              # у плитки-заголовка
    control: PnControl | None = None             # у плитки-управления


class PnScenario(Schema):
    card: PnCard
    flow: PnFlow
    tiles: list[PnTile]
    variables: dict[str, Any]


class PnTileIn(Schema):
    node: str = ""
    title: str = ""
    w: int = 6


class PnLayoutIn(Schema):
    tiles: list[PnTileIn]


class PnEntry(Schema):
    id: int
    kind: str
    text: str
    who: str
    node: str
    run: int | None
    at: dt.datetime


class PnJournal(Schema):
    entries: list[PnEntry]
    next: int | None


class PnActive(Schema):
    active: bool


WIDTHS = (3, 4, 6, 12)


def _num(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _card(graph):
    found = stats.of(graph)
    return PnCard(id=graph.pk, slug=graph.slug, title=graph.title, active=graph.active, running=found["running"], waiting=found["waiting"],
                  errors=sum(1 for p in check.problems(graph.doc, graph.slug, graph.owner) if p["level"] == "error"), here=flowmap.here_titles(graph))


def _controls(graph):
    """Управление сценария по порядку на холсте: node → PnControl."""
    flat = runtime.Doc(runtime.flatten(graph.doc, graph.slug))
    shared = runtime.variables(graph)
    found = {}
    for node_id, node in sorted(flat.nodes.items(), key=lambda item: (item[1].get("x") or 0, item[1].get("y") or 0)):
        kind = node.get("type")
        if kind not in nodes.CONTROLS:
            continue
        data = node.get("data") or {}
        name = str(data.get("name") or "").strip()
        found[node_id] = PnControl(node=node_id, kind=kind, name=name, value=None if kind == "manual" else runtime._dig(shared, name),
                                   options=[line.strip() for line in str(data.get("options") or "").splitlines() if line.strip()] if kind == "ctl_choice" else [],
                                   min=_num(data.get("min")) if kind == "ctl_number" else None, max=_num(data.get("max")) if kind == "ctl_number" else None,
                                   step=_num(data.get("step")) if kind == "ctl_number" else None)
    return found


def _tiles(graph, controls):
    """Раскладка пульта: сохранённый порядок и ширина, затем новые управления в конец. Устаревшие записи молча пропускаются."""
    tiles, used = [], set()
    for index, item in enumerate(graph.panel or []):
        if not isinstance(item, dict):
            continue
        w = item.get("w") if item.get("w") in WIDTHS else 6
        if item.get("node") in controls and item["node"] not in used:
            used.add(item["node"])
            tiles.append(PnTile(key=item["node"], w=w, control=controls[item["node"]]))
        elif item.get("title"):
            tiles.append(PnTile(key=f"title:{index}", w=12, title=str(item["title"])))
    tiles.extend(PnTile(key=node_id, w=6, control=control) for node_id, control in controls.items() if node_id not in used)
    return tiles


@router.get("/panel", response=list[PnCard])
def panel(request):
    return [_card(graph) for graph in Graph.objects.filter(owner="").order_by("title")]


@router.get("/{int:graph_id}/scenario", response=PnScenario)
def scenario(request, graph_id: int):
    graph = get_object_or_404(Graph, pk=graph_id, owner="")
    flow = flowmap.build(graph)
    return PnScenario(card=_card(graph), flow=PnFlow(**flow),
                      tiles=_tiles(graph, _controls(graph)), variables=runtime.variables(graph))


@router.put("/{int:graph_id}/layout", response=list[PnTile])
def set_layout(request, graph_id: int, body: PnLayoutIn):
    graph = get_object_or_404(Graph, pk=graph_id, owner="")
    controls = _controls(graph)
    if len(body.tiles) > 200:
        raise HttpError(400, "Слишком много плиток.")
    layout = []
    for tile in body.tiles:
        if tile.w not in WIDTHS:
            raise HttpError(400, "Ширина плитки: 3, 4, 6 или 12.")
        if tile.node:
            if tile.node in controls:
                layout.append({"node": tile.node, "w": tile.w})
        elif tile.title.strip():
            layout.append({"title": tile.title.strip()[:60], "w": 12})
    graph.panel = layout
    graph.save(update_fields=["panel"])
    return _tiles(graph, controls)


@router.get("/{int:graph_id}/journal", response=PnJournal)
def journal_page(request, graph_id: int, before: int | None = None, kind: str = ""):
    graph = get_object_or_404(Graph, pk=graph_id, owner="")
    rows, more = journal.page(graph, before=before, kind=kind)
    return PnJournal(entries=[PnEntry(id=r.pk, kind=r.kind, text=r.text, who=r.who, node=r.node, run=r.run, at=r.at) for r in rows], next=more)


@router.post("/{int:graph_id}/active", response=PnActive)
def set_active(request, graph_id: int, body: PnActive):
    graph = get_object_or_404(Graph, pk=graph_id)
    if graph.active != body.active:
        journal.note(graph, "switch", "Сценарий включён" if body.active else "Сценарий выключен", request.user.get_username())
    graph.active = body.active
    graph.save(update_fields=["active"])
    return PnActive(active=graph.active)


@router.post("/{int:graph_id}/reset", response=PnCard)
def reset(request, graph_id: int):
    graph = get_object_or_404(Graph, pk=graph_id)
    runtime.reset_scenario(graph)
    journal.note(graph, "reset", "Сценарий начат заново", request.user.get_username())
    return _card(graph)
