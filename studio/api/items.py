"""Объект: чтение, сохранение с проверкой версии, занятие (кто правит), история и предпросмотр.

Версия объекта это его updated_at: клиент присылает ту, с которой открыл, и если с тех пор объект сохранил кто-то
другой, ответ 409 с тем, кто и когда. force=true сохраняет поверх (чужая правка остаётся в истории).
"""
from datetime import date, datetime

from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from documents.editor import MAX_KEYS, MAX_TITLE_LEN, render_preview
from filesystem import history
from filesystem.models import Item, ItemRevision
from secure.requestkeys import keys_for_mode

router = Router(tags=["items"])

EDIT_FIELDS = ("name", "format", "body", "meta", "url", "world_created_at", "world_updated_at", "world_creator")


class Where(Schema):
    volume: int
    volume_name: str
    placement: int
    path: str


class Holder(Schema):
    user: str
    since: datetime


class ItemOut(Schema):
    id: int
    slug: str
    name: str
    format: str
    body: str
    meta: str
    url: str
    asset: str | None
    scene: str | None
    message: str | None
    world_created_at: date | None
    world_updated_at: date | None
    world_creator: str
    version: str
    updated_by: str | None
    updated_at: datetime
    created_at: datetime
    placements: list[Where]
    holder: Holder | None


class ItemIn(Schema):
    name: str
    format: str = ""
    body: str = ""
    meta: str = ""
    url: str = ""
    world_created_at: date | None = None
    world_updated_at: date | None = None
    world_creator: str = ""
    version: str
    force: bool = False


class Conflict(Schema):
    detail: str
    by: str | None
    at: datetime
    version: str


class Found(Schema):
    id: int
    slug: str
    name: str
    format: str


class Revision(Schema):
    id: int
    saved_at: datetime
    saved_by: str | None
    name: str
    format: str


class KeysSpec(Schema):
    mode: str = "all"            # all | none | custom
    slugs: list[str] = []        # для custom


class PreviewIn(Schema):
    format: str = ""
    title: str = ""
    body: str = ""
    meta: str = ""
    keys: KeysSpec = KeysSpec()


class Issue(Schema):
    line: int
    level: str
    code: str
    message: str


class PreviewOut(Schema):
    body: str
    infobox: str
    issues: dict[str, list[Issue]]


def _holder(item, user):
    lock = history.holder(item)
    if lock is None or lock.user_id == user.pk:
        return None
    return Holder(user=lock.user.get_username(), since=lock.acquired_at)


def _out(item, user):
    return ItemOut(
        id=item.pk, slug=item.slug, name=item.name, format=item.format, body=item.body, meta=item.meta, url=item.url,
        asset=item.asset.name if item.asset_id else None,
        scene=item.scene.slug if item.scene_id else None,
        message=str(item.message) if item.message_id else None,
        world_created_at=item.world_created_at, world_updated_at=item.world_updated_at, world_creator=item.world_creator,
        version=item.updated_at.isoformat(), updated_by=item.updated_by.get_username() if item.updated_by_id else None,
        updated_at=item.updated_at, created_at=item.created_at,
        placements=[
            Where(volume=p.volume_id, volume_name=p.volume.name or p.volume.slug, placement=p.pk, path=p.path())
            for p in item.placements.select_related("volume", "parent")
        ],
        holder=_holder(item, user),
    )


def _item(item_id):
    return get_object_or_404(Item.objects.select_related("asset", "scene", "message", "updated_by"), pk=item_id)


@router.get("", response=list[Found])
def search(request, q: str = ""):
    found = Item.objects.order_by("name")
    if q.strip():
        found = found.filter(Q(name__icontains=q.strip()) | Q(slug__icontains=q.strip()))
    return [Found(id=i.pk, slug=i.slug, name=i.name, format=i.format) for i in found[:30]]


@router.get("/{int:item_id}", response=ItemOut)
def read(request, item_id: int):
    return _out(_item(item_id), request.user)


@router.put("/{int:item_id}", response={200: ItemOut, 409: Conflict})
def save(request, item_id: int, body: ItemIn):
    item = _item(item_id)
    if item.updated_at.isoformat() != body.version and not body.force:
        by = item.updated_by.get_username() if item.updated_by_id else None
        return 409, Conflict(
            detail="Объект изменён после того, как вы его открыли.", by=by, at=item.updated_at, version=item.updated_at.isoformat(),
        )
    for field in EDIT_FIELDS:
        setattr(item, field, getattr(body, field))
    item.updated_by = request.user
    item.full_clean()
    item.save()
    return _out(_item(item_id), request.user)


@router.post("/{int:item_id}/lock", response={200: dict, 423: Holder})
def lock(request, item_id: int):
    """Занять объект на время правки (клиент повторяет раз в HEARTBEAT секунд). 423: объект правит другой."""
    other = history.acquire(_item(item_id), request.user)
    if other is not None:
        return 423, Holder(user=other.user.get_username(), since=other.acquired_at)
    return {"heartbeat": history.HEARTBEAT_SECONDS}


@router.delete("/{int:item_id}/lock")
def unlock(request, item_id: int):
    history.release(_item(item_id), request.user)
    return {}


@router.get("/{int:item_id}/revisions", response=list[Revision])
def revisions(request, item_id: int):
    found = ItemRevision.objects.filter(item_id=item_id).select_related("saved_by")[:100]
    return [
        Revision(id=r.pk, saved_at=r.saved_at, saved_by=r.saved_by.get_username() if r.saved_by_id else None, name=r.name, format=r.format)
        for r in found
    ]


@router.post("/preview", response=PreviewOut)
def preview(request, body: PreviewIn):
    keys = keys_for_mode(body.keys.mode, body.keys.slugs[:MAX_KEYS])
    return render_preview(body.format, body.title[:MAX_TITLE_LEN], body.body, body.meta, keys)
