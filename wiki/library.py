"""Вики поверх томов: раздел это том (или смонтированная папка тома), подраздел это папка, страница это объект формата-страницы.

Вики приложение, а не хранилище: оно показывает тома, подключённые к машине игрока, и ничего о них не хранит. Для одного запроса
дерево и страницы читаются целиком несколькими запросами (тома, размещения, объекты) и дальше работают в памяти.

Раздел и страница описаны объектами Node и Page с теми же полями, которые вики использует во всех своих видах (название, цепочка
родителей, условия доступа, текст), поэтому разметка, проверка доступа и поиск от устройства хранения не зависят.
"""
from machines.models import MachineMount

from filesystem.models import Placement, Volume
from filesystem.rawview import registry

# формат записи -> тип записи вики (так их называют шаблоны и значки)
DOC_TYPES = {"doc": "doc", "scan": "scan", "snp": "web", "rec": "rec"}
DEFAULT_TYPE = "doc"


def _machine(request):
    from .mounts import _machine as machine_of

    return machine_of(request)


class Node:
    """Раздел вики: корень (том) или папка внутри него."""

    def __init__(self, pk, name, parent, volume, access, hidden, slug=""):
        self.pk = pk
        self.name = name
        self.parent = parent
        self.volume = volume
        self.access = access or {}
        self.hidden = hidden
        self.slug = slug
        self.node = ""                       # «нода ведра» из прежней модели: у тома её нет

    @property
    def parent_id(self):
        return self.parent.pk if self.parent is not None else None

    def chain(self):
        """Цепочка от корня до этого раздела включительно."""
        nodes, node = [], self
        while node is not None:
            nodes.append(node)
            node = node.parent
        return nodes[::-1]

    def path(self):
        return ":".join(n.name for n in self.chain())

    def __str__(self):
        return self.path()


class Page:
    """Страница вики: объект формата-страницы, положенный в том."""

    storage_class = ""

    def __init__(self, placement, node, fmt):
        item = placement.item
        self.placement = placement
        self.item = item
        self.pk = placement.pk
        self.namespace = node
        self.title = item.name
        self.type = DOC_TYPES.get(item.format, DEFAULT_TYPE)
        self.ext = fmt.extension if fmt is not None and fmt.extension else f".{self.type}"
        self.body = item.body
        self.infobox = item.meta
        self.direct_link = item.slug
        self.world_date = item.world_updated_at
        self.updated_at = item.updated_at
        self.hidden = placement.hidden or placement.name.startswith(".")
        if placement.access_mode == Placement.Mode.REPLACE:
            self.access = placement.access or {}
        elif placement.access_mode == Placement.Mode.NONE:
            self.access = {}
        else:
            self.access = item.access or {}

    def path(self):
        parts = [n.name for n in self.namespace.chain()] if self.namespace else []
        return ":".join(parts + [self.title])

    def __str__(self):
        return self.path()


class Library:
    def __init__(self, nodes, pages):
        self.nodes = nodes
        self.pages = pages
        self.by_pk = {n.pk: n for n in nodes}
        self.by_name = {(n.parent_id, n.name): n for n in nodes}
        self._in = {}
        for page in pages:
            self._in.setdefault(page.namespace.pk, []).append(page)
        self.by_slug = {page.direct_link: page for page in pages}

    def pages_in(self, node):
        """Страницы раздела (без вложенных); node None: корня у вики нет, страниц там не бывает."""
        return sorted(self._in.get(node.pk, []), key=lambda page: page.title.casefold()) if node is not None else []

    def page_at(self, node, title):
        return next((page for page in self._in.get(node.pk, []) if page.title == title), None) if node is not None else None


def _pages_formats():
    return {found.name: found for found in registry.all_formats() if found.page}


def _volumes(request):
    """[(том, папка внутри тома или '')] в порядке показа: смонтированные на машину, а без машины все."""
    machine = _machine(request) if request is not None else None
    if machine is None:
        return [(volume, "") for volume in Volume.objects.order_by("slug")]
    seen, found = set(), []
    for mount in MachineMount.objects.filter(machine=machine).select_related("volume").order_by("order", "id"):
        if mount.volume_id not in seen:
            seen.add(mount.volume_id)
            found.append((mount.volume, mount.volume_path))
    return found


def build(request=None):
    """Дерево и страницы для запроса (машина игрока). Разделы без единой страницы вики не показываются."""
    formats = _pages_formats()
    volumes = _volumes(request)
    ids = [volume.pk for volume, _ in volumes]
    placements = list(Placement.objects.filter(volume_id__in=ids).select_related("item"))
    by_volume = {}
    for placement in placements:
        by_volume.setdefault(placement.volume_id, []).append(placement)

    nodes, pages = [], []
    for volume, prefix in volumes:
        rows = by_volume.get(volume.pk, [])
        by_id = {row.pk: row for row in rows}
        base = _prefix_folder(rows, prefix)
        if prefix and base is None:
            continue
        root = Node(-volume.pk, volume.name or volume.slug, None, volume, volume.access, False, slug=volume.slug)
        built = {base.pk if base is not None else None: root}
        volume_nodes, volume_pages = [root], []

        def node_for(placement_id):
            if placement_id in built:
                return built[placement_id]
            row = by_id[placement_id]
            parent = node_for(row.parent_id) if row.parent_id is not None else root
            node = Node(row.pk, row.name, parent, volume, row.access if row.access_mode != "none" else {}, row.hidden or row.name.startswith("."))
            built[placement_id] = node
            volume_nodes.append(node)
            return node

        for row in rows:
            if row.kind == Placement.Kind.FOLDER:
                if _under(row, by_id, base):
                    node_for(row.pk)
        for row in rows:
            if row.kind != Placement.Kind.ITEM or row.item.format not in formats or not _under(row, by_id, base):
                continue
            node = node_for(row.parent_id) if row.parent_id is not None and row.parent_id != (base.pk if base else None) else root
            volume_pages.append(Page(row, node, formats[row.item.format]))
        if volume_pages:
            nodes += volume_nodes
            pages += volume_pages
    return Library(nodes, pages)


def _prefix_folder(rows, prefix):
    """Папка тома по пути prefix (None: весь том)."""
    if not prefix:
        return None
    parent = None
    by_parent = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)
    for name in prefix.split("/"):
        parent = next((row for row in by_parent.get(parent.pk if parent else None, []) if row.name == name and row.kind == Placement.Kind.FOLDER), None)
        if parent is None:
            return None
    return parent


def _under(row, by_id, base):
    """Лежит ли размещение внутри папки base (None: везде в томе)."""
    if base is None:
        return True
    seen, parent_id = set(), row.parent_id
    while parent_id is not None and parent_id not in seen:
        if parent_id == base.pk:
            return True
        seen.add(parent_id)
        parent = by_id.get(parent_id)
        parent_id = parent.parent_id if parent is not None else None
    return False


def library(request):
    """Библиотека для запроса: читается один раз на запрос."""
    found = getattr(request, "_wiki_library", None)
    if found is None:
        found = build(request)
        request._wiki_library = found
    return found
