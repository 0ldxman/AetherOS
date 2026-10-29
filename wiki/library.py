"""Вики поверх томов: раздел это том (или смонтированная папка тома), подраздел это папка, страница это объект с текстом-разметкой
(формат с галочкой markup); остальные файлы раздела открываются во вьювере своего формата.

Вики приложение, а не хранилище: файл вики записи игрока подключает к ней папки хостов (тома на хостах смонтированы обычно, на клиенте их как дисков нет), и ничего о них она не хранит. Для одного запроса
дерево и страницы читаются целиком несколькими запросами (тома, размещения, объекты) и дальше работают в памяти.

Раздел и страница описаны объектами Node и Page с теми же полями, которые вики использует во всех своих видах (название, цепочка
родителей, условия доступа, текст), поэтому разметка, проверка доступа и поиск от устройства хранения не зависят.
"""
import itertools
import posixpath

from django.core import signing

from filesystem import rights
from filesystem.models import Placement, Volume
from documents.kinds import doc_type
from filesystem.content.rawview import registry

FILE_TYPE = "file"                       # не страница: файл формата без разметки, открывается во вьювере


def _machine(request):
    """Машина игрока для этого запроса или None (служебный вызов, нет сессии, нет такой машины)."""
    if not hasattr(request, "session") or not hasattr(request, "user"):
        return None

    from machines.current import current_machine
    from machines.models import Machine

    try:
        return current_machine(request)
    except Machine.DoesNotExist:
        return None


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
    """Запись раздела вики: страница (формат с разметкой) или файл другого формата, положенный в том."""

    storage_class = ""

    def __init__(self, placement, node, fmt, entry=None, view=None):
        item = placement.item
        self.markup = fmt is not None and fmt.markup
        self.entry, self.view = entry, view         # вид машины и запись в нём (раздел из файла вики); у сводки автора пусто
        self.placement = placement
        self.item = item
        self.pk = placement.pk
        self.namespace = node
        self.title = item.name
        self.type = doc_type(item.format) if self.markup else FILE_TYPE
        self.ext = fmt.extension if fmt is not None and fmt.extension else f".{self.type}"
        self.body = item.body if self.markup else ""
        self.infobox = item.meta if self.markup else ""
        self.direct_link = item.slug
        self.world_date = item.world_updated_at
        self.updated_at = item.updated_at
        self.updated_by = item.updated_by
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


def _formats():
    return {found.name: found for found in registry.all_formats()}


def _markup_formats():
    return {name for name, found in _formats().items() if found.markup}


def _sections(request, machine):
    """[(название, вид машины, путь в нём)] разделов, которые подключают файлы вики записи игрока.

    Строка volume файла вики называет хост, путь на нём и запись хоста; вики подключается к хосту как клиент и видит поддерево
    так, как его видит эта запись. Без хоста берётся эта же машина (права записи игрока). Недоступный хост даёт раздел, которого нет."""
    from urllib.parse import urlsplit

    from django.urls import Resolver404, resolve

    from filesystem.machine_view import view_for
    from machines.network import connection
    from machines.current import active_session, visible_apps
    from machines.access.groups import principal_for
    from machines.models import Machine

    apps = []
    for app in visible_apps(request, machine):
        try:
            if "wiki" in resolve(urlsplit(app.path).path).namespaces:
                apps.append(app)
        except Resolver404:
            continue
    lines = [line for app in apps for line in app.volumes]
    if not lines:
        return []
    signed = request.user.is_authenticated
    profile = active_session(request).profile if signed else None
    user = request.user if signed else None
    hosts = {found.hostname: found for found in Machine.objects.filter(hostname__in={line.host for line in lines if line.host})}

    sections = []
    for line in lines:
        if line.host:
            host = hosts.get(line.host)
            account = connection.account_of(host, line.user or "guest") if host is not None else None
            view = connection.connect(machine, host, line.path, account, user) if account is not None else None
        else:
            view = view_for(machine, user, principal_for(profile) if profile is not None else None)
        if view is not None and view.is_directory(line.path):
            sections.append((line.title or posixpath.basename(line.path) or line.host or machine.label, view, line.path))
    return sections


def build(request=None):
    """Дерево и страницы для запроса (машина игрока). Разделы без единой страницы вики не показываются.

    Без машины (служебные вызовы, сводка автора) берутся все тома; с машиной разделы называет файл вики записи игрока."""
    formats = _formats()
    machine = _machine(request) if request is not None else None
    if machine is None:
        return _from_volumes(formats, [(volume, "") for volume in Volume.objects.order_by("slug")])
    return _from_views(formats, _sections(request, machine))


def _from_views(formats, sections):
    nodes, pages, synthetic = [], [], itertools.count(-1, -1)
    for title, view, base in sections:
        entries = view.under(base)
        root_entry = entries[0]
        root_conditions = list(root_entry.conditions)
        root = Node(next(synthetic), title, None, None, {"all": root_conditions} if root_conditions else {}, False)
        built = {base: root}
        section_nodes, section_pages = [root], []

        def node_for(path):
            if path in built:
                return built[path]
            entry = view.get(path)
            placement = entry.placement if entry is not None else None
            parent = node_for(posixpath.dirname(path))
            access = placement.access if placement is not None and placement.access_mode != Placement.Mode.NONE else {}
            node = Node(placement.pk if placement is not None else next(synthetic), posixpath.basename(path), parent, None, access,
                        bool(entry and entry.hidden))
            built[path] = node
            section_nodes.append(node)
            return node

        for entry in entries[1:]:
            if entry.is_dir:
                node_for(entry.path)
        for entry in entries[1:]:
            if entry.is_dir or entry.item is None or entry.placement is None:
                continue
            try:
                rights.check(view, view.principal, entry.path, "r")
            except rights.Denied:
                continue
            section_pages.append(Page(entry.placement, node_for(posixpath.dirname(entry.path)), formats.get(entry.item.format), entry, view))
        if section_pages:
            nodes += section_nodes
            pages += section_pages
    return Library(nodes, pages)


def _is_markup(formats, name):
    return name in formats and formats[name].markup


def _from_volumes(formats, volumes):
    """Сводка автора: все тома, но только страницы (файлы других форматов открываются у игрока, в сводке им делать нечего)."""
    ids = [volume.pk for volume, _ in volumes]
    placements = list(Placement.objects.filter(volume_id__in=ids).select_related("item", "item__updated_by"))
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
            if row.kind != Placement.Kind.ITEM or not _is_markup(formats, row.item.format) or not _under(row, by_id, base):
                continue
            node = node_for(row.parent_id) if row.parent_id is not None and row.parent_id != (base.pk if base else None) else root
            volume_pages.append(Page(row, node, formats.get(row.item.format)))
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


def link_checker():
    """Проверка ссылок для линтера разметки (documents.markup.lint): по всем томам, как сводка автора; библиотека читается один раз."""
    lib = build(None)
    return lambda target: _link_exists(lib, target)


def _link_exists(lib, target):
    if target.startswith("go/"):
        return target[3:].strip("/") in lib.by_slug
    parts = [p for p in target.split("/") if p]
    if not parts or parts == ["search"]:
        return True
    current = None
    for part in parts[:-1]:
        current = lib.by_name.get((current.pk if current else None, part))
        if current is None:
            return False
    last = parts[-1]
    if (current.pk if current else None, last) in lib.by_name:
        return True
    return current is not None and lib.page_at(current, last) is not None


_SIGNER = signing.Signer(salt="wiki-file")


def locate_file(request, value):
    """Адрес ?wiki=<подписанный id> для вьюверов (filesystem.content.locate): файл раздела вики игрока, если он открыт.

    Адрес выдаёт сама вики тому, кто файл видел (в том числе скрытый, по прямой ссылке), поэтому id подписан: перебором чужие
    скрытые файлы не найти, а видимость второй раз не проверяется."""
    from secure.requestkeys import request_keys
    from wiki.access import document_state

    try:
        pk = int(_SIGNER.unsign(value))
    except (signing.BadSignature, ValueError):
        return None
    page = next((page for page in library(request).pages if page.pk == pk and page.entry is not None), None)
    if page is None or not document_state(page, request_keys(request), via_direct_link=True).open:
        return None
    return page.entry, page.view


def window_of(page):
    """Окно рабочего стола для файла раздела: документ, вьювер ассета, текст... (filesystem.content.window)."""
    from filesystem.content.window import resolve_content

    if page.entry is None:
        return None
    return resolve_content(page.entry, page.entry.path, posixpath.basename(page.entry.path), {"wiki": _SIGNER.sign(str(page.pk))})
