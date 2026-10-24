"""Где в вики используется ключ: условия доступа и разметка записей.

Нужно админке ключей, чтобы перед удалением или переименованием было видно,
что от него зависит.
"""
import json
import re

from django.db.models import Q, TextField
from django.db.models.functions import Cast

from .models import Document, Namespace


def _mentions(slug, *texts):
    pattern = re.compile(rf"(?<![\w-]){re.escape(slug)}(?![\w-])")
    return any(pattern.search(t or "") for t in texts)


def key_usage(slug):
    """(записи, разделы), которые упоминают ключ."""
    documents = (
        Document.objects.select_related("namespace__parent__parent__parent")
        .annotate(
            access_text=Cast("access", TextField()),
            visibility_text=Cast("visibility", TextField()),
        )
        .filter(
            Q(body__contains=slug)
            | Q(infobox__contains=slug)
            | Q(access_text__contains=slug)
            | Q(visibility_text__contains=slug)
        )
    )
    namespaces = (
        Namespace.objects.select_related("parent__parent__parent")
        .annotate(
            access_text=Cast("access", TextField()),
            visibility_text=Cast("visibility", TextField()),
        )
        .filter(Q(access_text__contains=slug) | Q(visibility_text__contains=slug))
    )
    return (
        [
            d for d in documents
            if _mentions(
                slug, d.body, d.infobox,
                json.dumps(d.access), json.dumps(d.visibility),
            )
        ],
        [
            n for n in namespaces
            if _mentions(slug, json.dumps(n.access), json.dumps(n.visibility))
        ],
    )
