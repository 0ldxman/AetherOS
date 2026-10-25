import hashlib
import re
from collections import defaultdict

from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe

from .access import document_state, namespace_state, request_keys
from .markup import render as render_markup, visible_text
from .models import Document, Namespace
from .mounts import mounted_roots

SEARCH_LIMIT = 100
SEARCH_MAX_LEN = 80


def _keys(request):
    return request_keys(request)


def _ns_path(ns):
    return "/".join(n.name for n in ns.chain())


def _path_text(ns):
    """Путь для шапки и выдачи: ~/Technologies/Weapon/ (корень: ~/)."""
    return f"~/{_ns_path(ns)}/" if ns else "~/"


def _address(ns):
    """Адрес раздела в запросе: technologies/weapon (корень: ~).

    Имена в нижнем регистре, пробелы заменены на "_", как в промпте.
    """
    if ns is None:
        return "~"
    return "/".join("_".join(n.name.lower().split()) for n in ns.chain())


def _ns_url(ns):
    return reverse("wiki:resolve", kwargs={"path": _ns_path(ns)})


def _doc_url(doc):
    parts = [_ns_path(doc.namespace)] if doc.namespace else []
    return reverse("wiki:resolve", kwargs={"path": "/".join(parts + [doc.title])})


def _crumbs(ns):
    # у видимого раздела видны и все родители, поэтому крошки безопасны
    return [{"name": n.name, "url": _ns_url(n)} for n in ns.chain()] if ns else []


def _prompt(request, ns):
    """Приглашение консоли БД: имя@слаг.

    Имя: логин игрока (в нижнем регистре, пробелы заменены на "_") или anon
    у гостя. Слаг: у ближайшего раздела вверх по цепочке, у которого он
    задан. Нет такого (или корень): root.
    """
    if request.user.is_authenticated:
        name = "_".join(request.user.get_username().lower().split()) or "anon"
    else:
        name = "anon"

    slug = "root"
    if ns is not None:
        for node in reversed(ns.chain()):
            if node.slug:
                slug = node.slug
                break

    return f"{name}@{slug}"


def _all_namespaces(request):
    """Все неймспейсы одним запросом, с уже привязанными родителями.

    Привязка нужна, чтобы chain() и namespace_state() не ходили в базу
    на каждый узел дерева. Список запоминается на запросе: путь, дерево
    и поиск в одном запросе читают таблицу один раз.
    """
    nodes = getattr(request, "_wiki_namespaces", None)
    if nodes is None:
        nodes = list(Namespace.objects.all())
        by_id = {n.pk: n for n in nodes}
        for n in nodes:
            if n.parent_id is not None:
                n.parent = by_id[n.parent_id]
        mounts = mounted_roots(request)
        if mounts is not None:
            # том, не смонтированный на машине, для игрока не существует: ни в дереве, ни в поиске
            nodes = [n for n in nodes if n.chain()[0].pk in mounts]
        request._wiki_namespaces = nodes
    return nodes


def _tree(request, keys, current):
    """Дерево неймспейсов для левой панели.

    Корень "~" виртуальный. Скрытые узлы в дерево не попадают, а у закрытых
    (но видимых) детей нет: за замок дерево не заглядывает.
    expanded только на пути к текущему неймспейсу, остальное раскрывает
    сам игрок.
    """
    children = defaultdict(list)
    for n in _all_namespaces(request):
        children[n.parent_id].append(n)

    on_path = {n.pk for n in current.chain()} if current else set()
    current_pk = current.pk if current else None

    mounts = mounted_roots(request)
    if mounts is not None:
        children[None].sort(key=lambda n: (mounts[n.pk], n.name))

    def build(parent_id, depth=0):
        result = []
        for ns in children[parent_id]:
            s = namespace_state(ns, keys)
            if not s.visible:
                continue
            result.append(
                {
                    "id": ns.pk,
                    "name": ns.name,
                    "url": _ns_url(ns),
                    "bucket": ns.parent_id is None,
                    "depth": depth,
                    "node": ns.node,
                    "open": s.open,
                    "current": ns.pk == current_pk,
                    "expanded": s.open and ns.pk in on_path,
                    "children": build(ns.pk, depth + 1) if s.open else [],
                }
            )
        return result

    buckets = build(None)

    return {
        "url": reverse("wiki:home"),
        "current": current is None,
        "children": buckets,
        "bucket_count": len(buckets),
        "nodes": sorted({b["node"] for b in buckets if b["node"]}),
    }


KIND_LABELS = {"doc": "document", "scan": "scan", "web": "snapshot", "rec": "record"}


_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARK = re.compile(r"[*_`>#~]+")


def _plain(text, title=""):
    """Текст записи для подписи и чтения: без директив (::...) и без первой строки, если она повторяет название."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("::", "#")):
            continue  # заголовок и так показан названием записи
        line = _MARK.sub("", _LINK.sub(r"\1", line)).strip()
        if line:
            lines.append(line)
    if lines and lines[0].casefold() == title.strip().casefold():
        lines.pop(0)
    return "\n".join(lines)


def _cut(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def _summary(plain):
    """Первая фраза записи: подпись в списке."""
    first = plain.split("\n", 1)[0] if plain else ""
    match = re.search(r"(?<=[.!?])\s", first)
    return _cut(first[: match.start()] if match else first, 90)


def _size_text(count):
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.1f} KB"
    return f"{count / (1024 * 1024):.1f} MB"


def _node_of(namespace):
    """Нода ведра: у корня цепочки; пусто, если не задана или записи вне ведра."""
    return namespace.chain()[0].node if namespace is not None else ""


def _key(namespace, name):
    """Ключ объекта в стиле S3: путь от ведра без «~», разделы через «/»."""
    parts = [n.name for n in namespace.chain()] if namespace is not None else []
    return "/".join(parts + [name])


def _uri(key):
    return f"aether://{key}"


def _modified(doc):
    """Last modified: дата в мире, если задана, иначе реальное время изменения (текст и ключ сортировки)."""
    if doc.world_date:
        d = doc.world_date
        return f"{d:%b} {d.day}, {d.year}", d.isoformat()
    t = doc.updated_at
    return f"{t:%b} {t.day}, {t.year}", t.isoformat()


def _doc_row(doc, state, keys):
    """Одна строка таблицы для записи (doc.namespace уже привязан).

    Размер, контрольная сумма, дата и класс хранения показываются только у открытой записи:
    у закрытой видны лишь название и тип.
    """
    url = _doc_url(doc)
    has_infobox = state.open and bool(doc.infobox.strip())

    size = etag = modified = storage = None
    modified_sort = ""
    nbytes = 0
    summary, excerpt = "restricted", ""
    if state.open:
        modified, modified_sort = _modified(doc)
        storage = doc.storage_class
        visible = visible_text(doc.body, keys)
        raw = visible.encode("utf-8")
        nbytes = len(raw)
        size = _size_text(nbytes)
        etag = hashlib.sha1(raw).hexdigest()[:10]
        plain = _plain(visible, doc.title)
        summary, excerpt = _summary(plain), _cut(plain, 520)

    return {
        "id": doc.pk,
        "title": doc.title,
        "ext": doc.ext,
        "type": doc.type,
        "kind": KIND_LABELS.get(doc.type, doc.type),
        "updated": doc.updated_at,
        "key": _key(doc.namespace, doc.title + doc.ext),
        "uri": _uri(_key(doc.namespace, doc.title + doc.ext)),
        "node": _node_of(doc.namespace),
        "modified": modified,
        "modified_sort": modified_sort,
        "storage": storage,
        "bytes": nbytes,
        "size": size,
        "etag": etag,
        "summary": summary,
        "excerpt": excerpt,
        "open": state.open,
        "url": url,
        "infobox_url": f"{url}?infobox=1" if has_infobox else None,
    }


def _doc_rows(ns, keys):
    """Строки таблицы документов неймспейса (только видимые)."""
    rows = []
    for doc in Document.objects.filter(namespace=ns):
        doc.namespace = ns  # чтобы не ходить в базу за родителем на каждой строке
        s = document_state(doc, keys)
        if not s.visible:
            continue
        rows.append(_doc_row(doc, s, keys))
    return rows


def _article_counts(request, keys):
    """Сколько видимых записей в каждом неймспейсе (с вложенными) и всего.

    Считаются только записи, которые игрок видит: скрытое и несмонтированное не попадает
    даже в число.
    """
    by_id = {n.pk: n for n in _all_namespaces(request)}
    counts = defaultdict(int)
    total = 0

    for doc in Document.objects.only("id", "namespace", "visibility", "access"):
        if doc.namespace_id is not None:
            if doc.namespace_id not in by_id:
                continue
            doc.namespace = by_id[doc.namespace_id]

        if not document_state(doc, keys).visible:
            continue

        total += 1
        if doc.namespace_id is not None:
            for node in doc.namespace.chain():
                counts[node.pk] += 1

    return counts, total


def _annotate_counts(nodes, counts):
    """Число видимых записей у каждого узла дерева (для подписей справа)."""
    for node in nodes:
        node["count"] = counts[node["id"]]
        _annotate_counts(node["children"], counts)


def _folders(tree, ns):
    """Подразделы текущего раздела (из дерева: скрытых и закрытых заглядываний там уже нет)."""
    if ns is None:
        return tree["children"]

    def find(nodes):
        for node in nodes:
            if node["id"] == ns.pk:
                return node["children"]
            found = find(node["children"])
            if found is not None:
                return found
        return None

    return find(tree["children"]) or []


def _path_bar(ns):
    """Кликабельный путь: ~ и разделы вплоть до текущего."""
    return [{"name": "Buckets", "url": reverse("wiki:home")}] + _crumbs(ns)


def _locked(request, title, crumbs=None):
    return render(
        request,
        "wiki/locked.html",
        {"title": title, "crumbs": crumbs},
        status=403,
    )


def _namespace_page(request, ns):
    keys = _keys(request)

    locked = False
    if ns is not None:
        state = namespace_state(ns, keys)
        if not state.visible:
            raise Http404
        locked = not state.open

    tree = _tree(request, keys, ns)
    crumbs = _path_bar(ns)
    documents = [] if locked else _doc_rows(ns, keys)
    folders = [] if locked else _folders(tree, ns)
    counts, total = _article_counts(request, keys)
    _annotate_counts(tree["children"], counts)
    nodes = {n.pk: n for n in _all_namespaces(request)}
    for folder in folders:
        folder["count"] = counts[folder["id"]]
        folder["key"] = _key(nodes[folder["id"]], "")      # заканчивается на «/»
        folder["uri"] = _uri(folder["key"])
        folder["node"] = _node_of(nodes[folder["id"]])

    return render(
        request,
        "wiki/explorer.html",
        {
            "tree": tree,
            "crumbs": crumbs,
            "folders": folders,
            "path_text": _path_text(ns),
            "at_root": ns is None,
            "prompt": _prompt(request, ns),
            "search_url": reverse("wiki:search"),
            "scope_address": _address(ns),
            "ns_id": ns.pk if ns else "",
            "locked": locked,
            # за замком даже список документов не отдаём
            "documents": documents,
            "total": total,
            "objects": len(documents),
            "total_here": len(documents) + len(folders),
            "prefixes": len(folders),
        },
        status=403 if locked else 200,
    )


def _document_page(request, doc, via_direct_link=False):
    keys = _keys(request)
    state = document_state(doc, keys, via_direct_link)
    if not state.visible:
        raise Http404

    # по прямой ссылке путь и название закрытой записи не раскрываем
    crumbs = None if via_direct_link else _crumbs(doc.namespace)

    if not state.open:
        return _locked(request, None if via_direct_link else doc.title, crumbs)

    # ?infobox=1: страница для отдельного окна с инфобоксом
    if request.GET.get("infobox"):
        if not doc.infobox.strip():
            raise Http404
        infobox_html = mark_safe(render_markup(doc.infobox, keys, "infobox"))
        return render(
            request,
            "wiki/infobox.html",
            {"doc": doc, "infobox_html": infobox_html},
        )

    infobox_url = None
    if via_direct_link and doc.infobox.strip():
        infobox_url = (
            reverse("wiki:direct", kwargs={"link": doc.direct_link})
            + "?infobox=1"
        )

    body_html = mark_safe(render_markup(doc.body, keys, "body"))
    return render(
        request,
        "wiki/document.html",
        {
            "doc": doc,
            "crumbs": crumbs,
            "body_html": body_html,
            "infobox_url": infobox_url,
        },
    )


def resolve(request, path=""):
    parts = [p for p in path.split("/") if p]
    if not parts:
        return _namespace_page(request, None)

    # путь разбирается по списку неймспейсов в памяти: один запрос на любую глубину
    by_name = {(n.parent_id, n.name): n for n in _all_namespaces(request)}

    current = None
    for part in parts[:-1]:
        current = by_name.get((current.pk if current else None, part))
        if current is None:
            raise Http404

    last = parts[-1]
    ns = by_name.get((current.pk if current else None, last))
    if ns is not None:
        return _namespace_page(request, ns)
    doc = Document.objects.filter(namespace=current, title=last).first()
    if doc is not None:
        doc.namespace = current  # уже с привязанными родителями
        return _document_page(request, doc)
    raise Http404


def direct(request, link):
    doc = Document.objects.filter(direct_link=link).first()
    if doc is None:
        raise Http404
    if doc.namespace_id is not None:
        by_id = {n.pk: n for n in _all_namespaces(request)}
        doc.namespace = by_id.get(doc.namespace_id)
        if doc.namespace is None:
            raise Http404  # том не смонтирован на этой машине
    return _document_page(request, doc, via_direct_link=True)


# =========================================================
# Поиск
# =========================================================

def _searchable_text(doc, keys):
    """Текст записи, по которому разрешено искать.

    Сюда попадает только то, что игрок и так может прочитать: закрытые
    ::spoiler вырезаны, иначе по факту совпадения можно узнать их содержимое.
    """
    return visible_text(doc.body, keys)


def search(request):
    """GET ?q=слово&ns=id раздела -> {"rows": [...]}.

    ns: раздел, из которого ищет игрок (пусто = корень). Ищем в нём и во
    всех вложенных разделах. Показываем только видимое: записи в закрытом
    разделе в выдачу не попадают совсем (как и в проводнике). Закрытая
    запись в открытом разделе находится только по названию, её текст
    не просматривается.
    """
    word = request.GET.get("q", "").strip()[:SEARCH_MAX_LEN]
    if not word:
        return JsonResponse({"rows": []})

    keys = _keys(request)
    all_ns = _all_namespaces(request)
    namespaces = {n.pk: n for n in all_ns}

    scope = None
    raw_scope = request.GET.get("ns", "")
    if raw_scope:
        try:
            scope = namespaces.get(int(raw_scope))
        except ValueError:
            scope = None

        if scope is None:
            return JsonResponse({"rows": []})

        # из закрытого или скрытого раздела искать нельзя
        scope_state = namespace_state(scope, keys)
        if not (scope_state.visible and scope_state.open):
            return JsonResponse({"rows": []})

    # предварительный отбор в базе, точная проверка дальше в Python
    candidates = Document.objects.filter(
        Q(title__icontains=word) | Q(body__icontains=word)
    )

    if scope is not None:
        # раздел и все его потомки (chain() каждого содержит раздел)
        in_scope = {
            n.pk
            for n in all_ns
            if any(x.pk == scope.pk for x in n.chain())
        }
        candidates = candidates.filter(namespace_id__in=in_scope)

    needle = word.casefold()

    rows = []
    for doc in candidates:
        if doc.namespace_id is not None and doc.namespace_id not in namespaces:
            continue  # том не смонтирован на этой машине
        doc.namespace = namespaces.get(doc.namespace_id)

        if doc.namespace is not None:
            ns_state = namespace_state(doc.namespace, keys)
            if not (ns_state.visible and ns_state.open):
                continue

        s = document_state(doc, keys)
        if not s.visible:
            continue

        found = needle in doc.title.casefold()
        if not found and s.open:
            found = needle in _searchable_text(doc, keys).casefold()
        if not found:
            continue

        row = _doc_row(doc, s, keys)
        row.pop("updated", None)  # в выдаче не нужно, и datetime лишний в JSON
        row["path"] = _key(doc.namespace, "")
        rows.append(row)

    rows.sort(key=lambda r: (r["path"], r["title"].casefold()))
    return JsonResponse({"rows": rows[:SEARCH_LIMIT]})