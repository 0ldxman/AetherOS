"""Где в вики используется ключ: разметка записей.

Условия доступа записей и разделов лежат в объектах, размещениях и томах, их находит secure.usage.
Здесь только упоминания ключа в тексте и врезке страниц.
"""
import json
import re

from filesystem.models import Item
from .library import _pages_formats


def _mentions(slug, *texts):
    pattern = re.compile(rf"(?<![\w-]){re.escape(slug)}(?![\w-])")
    return any(pattern.search(t or "") for t in texts)


def key_usage(slug):
    """Объекты страниц, в тексте или врезке которых упомянут ключ."""
    candidates = Item.objects.filter(body__contains=slug) | Item.objects.filter(meta__contains=slug)
    return [
        item for item in candidates.distinct()
        if item.format in _pages_formats() and _mentions(slug, item.body, json.dumps(item.meta))
    ]
