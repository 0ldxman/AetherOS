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


def _locked(request, title, crumbs=None):
    return render(
        request,
        "wiki/locked.html",
        {"title": title, "crumbs": crumbs},
        status=403,
    )


def _namespace_page(request, ns):
    keys = _keys(request)
    if ns is not None:
        state = namespace_state(ns, keys)
        if not state.visible:
            raise Http404
        if not state.open:
            return _locked(request, ns.name, _crumbs(ns))

    namespaces = []
    for child in Namespace.objects.filter(parent=ns):
        s = namespace_state(child, keys)
        if s.visible:
            namespaces.append(
                {"name": child.name, "url": _ns_url(child), "open": s.open}
            )

    documents = []
    for doc in Document.objects.filter(namespace=ns):
        s = document_state(doc, keys)
        if s.visible:
            documents.append(
                {"name": doc.title, "url": _doc_url(doc), "open": s.open}
            )

    return render(
        request,
        "wiki/listing.html",
        {
            "title": ns.name if ns else "Вики",
            "crumbs": _crumbs(ns),
            "namespaces": namespaces,
            "documents": documents,
        },
    )


def _document_page(request, doc, via_direct_link=False):
    state = document_state(doc, _keys(request), via_direct_link)
    if not state.visible:
        raise Http404
    # по прямой ссылке путь и название закрытой записи не раскрываем
    crumbs = None if via_direct_link else _crumbs(doc.namespace)
    if not state.open:
        return _locked(request, None if via_direct_link else doc.title, crumbs)
    return render(
        request,
        "wiki/document.html",
        {"doc": doc, "crumbs": crumbs},
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