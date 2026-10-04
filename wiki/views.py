from collections import defaultdict

from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe

from .access import document_state, namespace_state, player_keys
from .markup import render as render_markup, visible_text
from .models import Document, Namespace

SEARCH_LIMIT = 100
SEARCH_MAX_LEN = 80


def _keys(request):
    return player_keys(request.user)


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


def _all_namespaces():
    """Все неймспейсы одним запросом, с уже привязанными родителями.

    Привязка нужна, чтобы chain() и namespace_state() не ходили в базу
    на каждый узел дерева.
    """
    nodes = list(Namespace.objects.all())
    by_id = {n.pk: n for n in nodes}
    for n in nodes:
        if n.parent_id is not None:
            n.parent = by_id[n.parent_id]
    return nodes


def _tree(keys, current):
    """Дерево неймспейсов для левой панели.

    Корень "~" виртуальный. Скрытые узлы в дерево не попадают, а у закрытых
    (но видимых) детей нет: за замок дерево не заглядывает.
    expanded только на пути к текущему неймспейсу, остальное раскрывает
    сам игрок.
    """
    children = defaultdict(list)
    for n in _all_namespaces():
        children[n.parent_id].append(n)

    on_path = {n.pk for n in current.chain()} if current else set()
    current_pk = current.pk if current else None

    def build(parent_id):
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
                    "open": s.open,
                    "current": ns.pk == current_pk,
                    "expanded": s.open and ns.pk in on_path,
                    "children": build(ns.pk) if s.open else [],
                }
            )
        return result

    return {
        "url": reverse("wiki:home"),
        "current": current is None,
        "children": build(None),
    }


def _doc_row(doc, state):
    """Одна строка таблицы для записи (doc.namespace уже привязан)."""
    url = _doc_url(doc)
    has_infobox = state.open and bool(doc.infobox.strip())

    return {
        "id": doc.pk,
        "title": doc.title,
        "ext": doc.ext,
        "updated": doc.updated_at,
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
        rows.append(_doc_row(doc, s))
    return rows


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

    return render(
        request,
        "wiki/explorer.html",
        {
            "tree": _tree(keys, ns),
            "path_text": _path_text(ns),
            "prompt": _prompt(request, ns),
            "search_url": reverse("wiki:search"),
            "scope_address": _address(ns),
            "ns_id": ns.pk if ns else "",
            "locked": locked,
            # за замком даже список документов не отдаём
            "documents": [] if locked else _doc_rows(ns, keys),
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

    body_html = mark_safe(render_markup(doc.body, keys, "body"))
    return render(
        request,
        "wiki/document.html",
        {"doc": doc, "crumbs": crumbs, "body_html": body_html},
    )


def resolve(request, path=""):
    parts = [p for p in path.split("/") if p]
    if not parts:
        return _namespace_page(request, None)

    current = None
    for part in parts[:-1]:
        current = Namespace.objects.filter(parent=current, name=part).first()
        if current is None:
            raise Http404

    last = parts[-1]
    ns = Namespace.objects.filter(parent=current, name=last).first()
    if ns is not None:
        return _namespace_page(request, ns)
    doc = Document.objects.filter(namespace=current, title=last).first()
    if doc is not None:
        return _document_page(request, doc)
    raise Http404


def direct(request, link):
    doc = Document.objects.filter(direct_link=link).first()
    if doc is None:
        raise Http404
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
    all_ns = _all_namespaces()
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

        row = _doc_row(doc, s)
        row.pop("updated", None)  # в выдаче не нужно, и datetime лишний в JSON
        row["path"] = _path_text(doc.namespace)
        rows.append(row)

    rows.sort(key=lambda r: (r["path"], r["title"].casefold()))
    return JsonResponse({"rows": rows[:SEARCH_LIMIT]})