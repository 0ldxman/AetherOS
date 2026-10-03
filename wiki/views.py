from collections import defaultdict

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from .access import document_state, guest_keys, namespace_state
from .models import Document, Namespace


def _keys(request):
    # позже здесь будут настоящие ключи игрока
    return guest_keys()


def _ns_path(ns):
    return "/".join(n.name for n in ns.chain())


def _ns_url(ns):
    return reverse("wiki:resolve", kwargs={"path": _ns_path(ns)})


def _doc_url(doc):
    parts = [_ns_path(doc.namespace)] if doc.namespace else []
    return reverse("wiki:resolve", kwargs={"path": "/".join(parts + [doc.title])})


def _crumbs(ns):
    # у видимого раздела видны и все родители, поэтому крошки безопасны
    return [{"name": n.name, "url": _ns_url(n)} for n in ns.chain()] if ns else []


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

    Корень "." виртуальный. Скрытые узлы в дерево не попадают, а у закрытых
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


def _doc_rows(ns, keys):
    """Строки таблицы документов неймспейса (только видимые)."""
    rows = []
    for doc in Document.objects.filter(namespace=ns):
        doc.namespace = ns  # чтобы не ходить в базу за родителем на каждой строке
        s = document_state(doc, keys)
        if not s.visible:
            continue

        url = _doc_url(doc)
        has_infobox = s.open and bool(doc.infobox.strip())

        rows.append(
            {
                "id": doc.pk,
                "title": doc.title,
                "type": doc.get_type_display(),
                "updated": doc.updated_at,
                "open": s.open,
                "url": url,
                "infobox_url": f"{url}?infobox=1" if has_infobox else None,
            }
        )
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
            "path_text": ns.path() if ns else ".",
            "locked": locked,
            # за замком даже список документов не отдаём
            "documents": [] if locked else _doc_rows(ns, keys),
        },
        status=403 if locked else 200,
    )


def _document_page(request, doc, via_direct_link=False):
    state = document_state(doc, _keys(request), via_direct_link)
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
        return render(request, "wiki/infobox.html", {"doc": doc})

    return render(request, "wiki/document.html", {"doc": doc, "crumbs": crumbs})


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