"""Сводка для автора: что менялось, что висит без связей, что сломано.

Считается по всем записям за один проход (тексты читаются целиком), поэтому
для очень большой вики стоит кэшировать. Данные только из вики: ключи и
ассеты, которыми пользуются машины и файловая система, здесь не видны.
"""
import re
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model

from assets.models import Asset
from secure.models import Key

from .markup.lint import ERROR, _Scan, _slugs, _wiki_target
from .models import Document, Namespace

RECENT_LIMIT = 15
LIST_LIMIT = 50

_ASSET_PREFIX = re.compile(r"^asset:")


@dataclass
class Dashboard:
    recent: list = field(default_factory=list)
    orphans: list = field(default_factory=list)       # записи без входящих ссылок
    broken: list = field(default_factory=list)        # записи с ошибками разметки
    unused_assets: list = field(default_factory=list)
    unused_keys: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)


def _path(doc, by_id):
    names = []
    ns = by_id.get(doc.namespace_id)
    while ns is not None:
        names.append(ns.name)
        ns = by_id.get(ns.parent_id)
    return ":".join(names[::-1] + [doc.title])


def _resolver(namespaces, documents):
    """Функция: путь из ссылки -> id записи (или None)."""
    by_name = {(n.parent_id, n.name): n for n in namespaces}
    by_title = {(d.namespace_id, d.title): d.pk for d in documents}
    by_link = {d.direct_link: d.pk for d in documents if d.direct_link}

    def resolve(target):
        if target.startswith("go/"):
            return by_link.get(target[3:].strip("/"))
        parts = [p for p in target.split("/") if p]
        current = None
        for part in parts[:-1]:
            current = by_name.get((current.pk if current else None, part))
            if current is None:
                return None
        if not parts:
            return None
        return by_title.get((current.pk if current else None, parts[-1]))

    return resolve


def build():
    namespaces = list(Namespace.objects.all())
    by_id = {n.pk: n for n in namespaces}
    documents = list(Document.objects.select_related("updated_by"))
    resolve = _resolver(namespaces, documents)

    incoming = {d.pk: 0 for d in documents}
    asset_refs, key_slugs, broken = set(), set(), []

    for doc in documents:
        problems = []
        for text in (doc.body, doc.infobox):
            scan = _Scan(text)
            problems += [i for i in scan.issues if i.level == ERROR]
            key_slugs.update(slug for _, slug in scan.keys)
            for _, _, ref in scan.assets:
                asset_refs.add(_ASSET_PREFIX.sub("", ref.lower()))
            for _, href in scan.links:
                target = _wiki_target(href)
                found = resolve(target) if target is not None else None
                if found is not None and found != doc.pk:
                    incoming[found] += 1
        for condition in (doc.access, doc.visibility):
            if condition:
                key_slugs.update(_slugs(condition))
        if problems:
            broken.append((doc, len(problems)))

    for ns in namespaces:
        for condition in (ns.access, ns.visibility):
            if condition:
                key_slugs.update(_slugs(condition))

    result = Dashboard()
    result.recent = [
        (d, _path(d, by_id))
        for d in sorted(documents, key=lambda d: d.updated_at, reverse=True)[:RECENT_LIMIT]
    ]
    result.orphans = [(d, _path(d, by_id)) for d in documents if incoming[d.pk] == 0]
    result.orphans.sort(key=lambda row: row[1])
    result.broken = [(d, _path(d, by_id), count) for d, count in broken]
    result.unused_assets = [
        a for a in Asset.objects.order_by("name")
        if (a.slug or "") not in asset_refs and str(a.public_id) not in asset_refs
    ]
    result.unused_keys = list(Key.objects.exclude(slug__in=key_slugs).order_by("slug"))
    result.totals = {
        "documents": len(documents),
        "namespaces": len(namespaces),
        "assets": Asset.objects.count(),
        "keys": Key.objects.count(),
        "authors": get_user_model().objects.filter(is_staff=True).count(),
    }
    return result
