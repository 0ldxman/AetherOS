"""Сводка для автора: что менялось, что висит без связей, что сломано.

Считается по всем записям за один проход (тексты читаются целиком), поэтому
для очень большой вики стоит кэшировать. Ассеты считаются только по
вики (файловая система машин ссылается на них по адресу, здесь это не видно);
ключи учитываются и в вики, и в условиях машин, и среди ключей файлов.
"""
import re
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model

from assets.models import Asset
from secure.access import condition_slugs
from secure.models import Key
from secure.usage import used_slugs

from .markup.lint import ERROR, _Scan, _wiki_target
from . import library

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


def _resolver(lib):
    """Функция: путь из ссылки -> id страницы (или None)."""

    def resolve(target):
        if target.startswith("go/"):
            found = lib.by_slug.get(target[3:].strip("/"))
            return found.pk if found is not None else None
        parts = [p for p in target.split("/") if p]
        if not parts:
            return None
        current = None
        for part in parts[:-1]:
            current = lib.by_name.get((current.pk if current else None, part))
            if current is None:
                return None
        found = lib.page_at(current, parts[-1])
        return found.pk if found is not None else None

    return resolve


def build():
    lib = library.build(None)                       # все тома, а не только смонтированные на машину игрока
    documents = lib.pages
    resolve = _resolver(lib)

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
        if doc.access:
            key_slugs.update(condition_slugs(doc.access))
        if problems:
            broken.append((doc, len(problems)))

    for node in lib.nodes:
        if node.access:
            key_slugs.update(condition_slugs(node.access))

    result = Dashboard()
    result.recent = [(d, d.path()) for d in sorted(documents, key=lambda d: d.updated_at, reverse=True)[:RECENT_LIMIT]]
    result.orphans = [(d, d.path()) for d in documents if incoming[d.pk] == 0]
    result.orphans.sort(key=lambda row: row[1])
    result.broken = [(d, d.path(), count) for d, count in broken]
    result.unused_assets = [
        a for a in Asset.objects.order_by("name")
        if (a.slug or "") not in asset_refs and str(a.public_id) not in asset_refs
    ]
    key_slugs |= used_slugs()  # условия машин и ключи файлов
    result.unused_keys = list(Key.objects.exclude(slug__in=key_slugs).order_by("slug"))
    result.totals = {
        "documents": len(documents),
        "namespaces": len(lib.nodes),
        "assets": Asset.objects.count(),
        "keys": Key.objects.count(),
        "authors": get_user_model().objects.filter(is_staff=True).count(),
    }
    return result
