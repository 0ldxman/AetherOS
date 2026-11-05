"""Конструктор условия доступа: текст выражения <-> дерево условий. Логика в documents.markup.expr."""
from typing import Any

from ninja import Router, Schema

from documents.markup.expr import SpoilerSyntaxError, format_expr, parse_expr

router = Router(tags=["access"])


class AccessSource(Schema):
    text: str


class AccessParsed(Schema):
    ok: bool
    error: str
    tree: Any = None           # ключ (строка) или {"not": …}, {"all": […]}, {"any": […]}; null при пустом условии


class AccessTreeIn(Schema):
    tree: Any = None


class AccessText(Schema):
    text: str
    error: str


@router.post("/parse", response=AccessParsed)
def parse(request, body: AccessSource):
    if not body.text.strip():
        return AccessParsed(ok=True, error="", tree=None)
    try:
        return AccessParsed(ok=True, error="", tree=parse_expr(body.text))
    except SpoilerSyntaxError as error:
        return AccessParsed(ok=False, error=str(error), tree=None)


@router.post("/format", response=AccessText)
def format_tree(request, body: AccessTreeIn):
    if body.tree is None:
        return AccessText(text="", error="")
    try:
        return AccessText(text=format_expr(body.tree), error="")
    except SpoilerSyntaxError as error:
        return AccessText(text="", error=str(error))
