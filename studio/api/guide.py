"""Справка автора: страницы docs/guide. Логика в guide.pages."""
from django.http import Http404
from django.urls import reverse
from ninja import Router, Schema

from guide import pages

router = Router(tags=["guide"])


class GdPage(Schema):
    slug: str
    title: str


class GdSection(Schema):
    title: str
    pages: list[GdPage]


class GdHead(Schema):
    id: str
    title: str
    level: int


class GdOut(Schema):
    slug: str
    title: str
    section: str
    html: str
    heads: list[GdHead]
    prev: GdPage | None
    next: GdPage | None
    missing: int                  # сколько картинок и видео страницы ещё не снято


class GdHit(Schema):
    slug: str
    title: str
    section: str
    snippet: str


def _short(page):
    return dict(slug=page.slug, title=page.title)


def _media_url(name):
    return reverse("studio_guide_media", kwargs={"name": name})


@router.get("", response=list[GdSection])
def index(request):
    return [dict(title=title, pages=[_short(p) for p in group]) for title, group in pages.sections()]


@router.get("/search", response=list[GdHit])
def find(request, q: str = ""):
    return [dict(_short(p), section=p.section, snippet=snippet) for p, snippet in pages.search(q)]


@router.get("/{slug}", response=GdOut)
def page(request, slug: str):
    found = pages.get(slug)
    if found is None:
        raise Http404
    everything = pages.pages()
    at = everything.index(next(p for p in everything if p.slug == slug))
    body, heads = pages.render(found, _media_url)
    gone = sum(1 for slug_, _ in pages.missing_media() if slug_ == slug)
    return dict(slug=found.slug, title=found.title, section=found.section, html=body, heads=heads,
                prev=_short(everything[at - 1]) if at else None,
                next=_short(everything[at + 1]) if at + 1 < len(everything) else None, missing=gone)
