"""Окно документа: файл формата с разметкой (doc, scan, snp, rec), разобранный парсером и в стилях своего типа.

Файл ищется по адресу запроса (filesystem.content.locate): из файлов игрока или из раздела вики, окну всё равно.
Закрытый файл (условия по ключам или слои, которые игрок ещё не снял) показывается замком. Врезка открывается рядом своим
окном (?infobox=1).
"""
import posixpath
from types import SimpleNamespace

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe

from documents.kinds import doc_type
from documents.markup import render as render_markup
from filesystem.content.locate import address_of, locate, query
from filesystem.content.rawview import registry
from filesystem.content.window import layers_block
from secure.access import satisfied
from secure.requestkeys import request_keys


def page_url(address, **extra):
    return reverse("documents:page") + "?" + query(address, **extra)


def page(request):
    entry, _ = locate(request)
    item = entry.item
    found = registry.format_named(item.format) if item is not None and item.format else None
    if found is None or not found.markup:
        raise Http404

    keys = request_keys(request)
    name = posixpath.basename(entry.path)
    title = name[: -len(found.extension)] if found.extension and name.endswith(found.extension) else name
    doc = SimpleNamespace(pk=item.pk, title=title, type=doc_type(item.format))

    if layers_block(entry) or not all(satisfied(condition, keys) for condition in entry.conditions):
        return render(request, "documents/locked.html", {"title": title})

    infobox = item.meta
    if request.GET.get("infobox"):
        if not infobox.strip():
            raise Http404
        return render(request, "documents/infobox.html", {"doc": doc, "infobox_html": mark_safe(render_markup(infobox, keys, "infobox"))})

    return render(request, "documents/document.html", {
        "doc": doc,
        "body_html": mark_safe(render_markup(entry.body, keys, "body")),
        "infobox_url": page_url(address_of(request), infobox=1) if infobox.strip() else None,
    })
