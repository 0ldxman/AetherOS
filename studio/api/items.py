"""Объект: чтение, сохранение с проверкой версии, занятие (кто правит), история и предпросмотр.

Версия объекта это его updated_at: клиент присылает ту, с которой открыл, и если с тех пор объект сохранил кто-то
другой, ответ 409 с тем, кто и когда. force=true сохраняет поверх (чужая правка остаётся в истории).
"""
from datetime import date, datetime

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from documents.editor import MAX_KEYS, MAX_TITLE_LEN, render_preview
from filesystem import history
from filesystem.manager import filemanager
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
    protected: bool            # есть условие доступа или слои
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


class LibraryRow(Schema):
    id: int
    slug: str
    name: str
    format: str
    kind: str                 # text | asset | link | scene | message | empty
    size: int | None
    places: int
    archives: int
    layers: bool
    access: bool
    updated_at: datetime
    updated_by: str | None


class Placed(Schema):
    placement: int
    volume: int
    parent: int | None        # папка в томе (для перехода)
    volume_name: str
    volume_slug: str
    path: str
    owner: str
    group: str
    mode: str
    hidden: bool
    own_access: bool          # у места своё условие (или снятое) вместо объектного
    own_state: bool           # у места свои слои (или снятые) вместо объектных


class InArchive(Schema):
    archive: int
    name: str
    path: str


class Mention(Schema):
    kind: str                 # письмо | сеть | вложен как ключ | подпись
    label: str


class Players(Schema):
    copies: int               # файлов игроков, которые ссылаются на объект (копии, перенесённое)
    edits: int                # из них с правкой текста игроком
    users: list[str]


class Whereabouts(Schema):
    placements: list[Placed]
    archives: list[InArchive]
    members: list[InArchive]  # если объект сам архив
    mentions: list[Mention]
    players: Players
    holders: list[Mention]    # что не даст удалить объект


class PutIn(Schema):
    volume: int
    parent: int | None = None
    name: str = ""


class DetachIn(Schema):
    placement: int


class RevisionOut(Schema):
    id: int
    saved_at: datetime
    saved_by: str | None
    name: str
    format: str
    body: str
    meta: str
    changes: dict             # поле -> [было, стало] или [[вид, строка], ...] (filesystem.history.compare с текущим)


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
    only: str = ""               # body | infobox: рисовать только открытую страницу


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
        version=item.updated_at.isoformat(), protected=bool(item.access) or bool(item.state.strip()), updated_by=item.updated_by.get_username() if item.updated_by_id else None,
        updated_at=item.updated_at, created_at=item.created_at,
        placements=[
            Where(volume=p.volume_id, volume_name=p.volume.name or p.volume.slug, placement=p.pk, path=p.path())
            for p in item.placements.select_related("volume", "parent")
        ],
        holder=_holder(item, user),
    )


def _item(item_id):
    return get_object_or_404(Item.objects.select_related("asset", "scene", "message", "updated_by"), pk=item_id)


KINDS = {
    "text": Q(asset__isnull=True, url="", scene__isnull=True, message__isnull=True) & ~Q(body=""),
    "asset": Q(asset__isnull=False),
    "link": ~Q(url=""),
    "scene": Q(scene__isnull=False),
    "message": Q(message__isnull=False),
    "empty": Q(asset__isnull=True, url="", scene__isnull=True, message__isnull=True, body=""),
}


@router.get("", response=list[LibraryRow])
def library(request, q: str = "", format: str = "", kind: str = "", only: str = "", limit: int = 200):
    """Библиотека объектов. only: orphans (нигде не лежит), shared (лежит в нескольких местах), layers (со слоями),
    access (с условием доступа), keys (объекты-ключи), mine (правил я), recent (правили за неделю)."""
    from datetime import timedelta

    from django.utils import timezone

    from filesystem.models import KEY_FORMAT

    found = Item.objects.select_related("updated_by").annotate(
        placement_count=Count("placements", distinct=True), archive_count=Count("in_archives", distinct=True),
    )
    words = q.strip()
    if words:
        found = found.filter(Q(name__icontains=words) | Q(slug__icontains=words) | Q(body__icontains=words))
    if format:
        found = found.filter(format=format)
    if kind in KINDS:
        found = found.filter(KINDS[kind])
    if only == "orphans":
        found = found.filter(placement_count=0, archive_count=0)
    elif only == "shared":
        found = found.filter(placement_count__gt=1)
    elif only == "layers":
        found = found.exclude(state="")
    elif only == "access":
        found = found.exclude(access={})
    elif only == "keys":
        found = found.filter(format=KEY_FORMAT)
    elif only == "mine":
        found = found.filter(updated_by=request.user)
    elif only == "recent":
        found = found.filter(updated_at__gte=timezone.now() - timedelta(days=7))
    rows = found.order_by("-updated_at")[: max(1, min(limit, 500))]
    return [
        LibraryRow(
            id=i.pk, slug=i.slug, name=i.name, format=i.format, kind=_kind(i), size=i.size if i.size is not None else (len(i.body.encode()) or None),
            places=i.placement_count, archives=i.archive_count, layers=bool(i.state.strip()), access=bool(i.access),
            updated_at=i.updated_at, updated_by=i.updated_by.get_username() if i.updated_by_id else None,
        )
        for i in rows
    ]


def _kind(item):
    if item.asset_id:
        return "asset"
    if item.url:
        return "link"
    if item.scene_id:
        return "scene"
    if item.message_id:
        return "message"
    return "text" if item.body else "empty"


class NewItem(Schema):
    name: str
    format: str = ""
    slug: str = ""
    volume: int | None = None     # сразу положить в корень этого тома


class ItemCreated(Schema):
    id: int


@router.post("", response=ItemCreated)
def create(request, body: NewItem):
    from filesystem.models import Volume

    volume = get_object_or_404(Volume, pk=body.volume) if body.volume else None
    return ItemCreated(id=filemanager.new_item(body.name, body.format, body.slug, volume).pk)


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
    old_filename = item.default_filename
    for field in EDIT_FIELDS:
        setattr(item, field, getattr(body, field))
    item.updated_by = request.user
    item.full_clean()
    item.save()
    filemanager.follow_filename(item, old_filename)
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
    return render_preview(body.format, body.title[:MAX_TITLE_LEN], body.body, body.meta, keys, body.only)


@router.get("/{int:item_id}/where", response=Whereabouts)
def where(request, item_id: int):
    """Где объект лежит и кто на него ссылается: тома, архивы, письма, сеть, файлы игроков."""
    from filesystem.manager.filemanager import holders

    item = _item(item_id)
    placements = item.placements.select_related("volume", "parent")
    mentions = [Mention(kind="письмо", label=str(a.message)) for a in item.mail_attachments.select_related("message")]
    mentions += [Mention(kind="сеть", label=f"{n.resource.address}{n.path}") for n in item.net_nodes.select_related("resource")]
    files = item.player_files.filter(deleted_at__isnull=True).select_related("user")
    return Whereabouts(
        placements=[
            Placed(placement=p.pk, volume=p.volume_id, parent=p.parent_id, volume_name=p.volume.name or p.volume.slug, volume_slug=p.volume.slug, path=p.path(), owner=p.owner, group=p.group,
                   mode=p.mode, hidden=p.hidden, own_access=p.access_mode != "inherit", own_state=p.state_mode != "inherit")
            for p in placements
        ],
        archives=[InArchive(archive=m.archive_id, name=m.archive.name, path=m.path) for m in item.in_archives.select_related("archive")],
        members=[InArchive(archive=m.item_id, name=m.item.name, path=m.path) for m in item.members.select_related("item")],
        mentions=mentions,
        players=Players(copies=files.count(), edits=files.exclude(content=None).count(),
                        users=sorted({f.user.get_username() for f in files})),
        holders=[Mention(kind=kind, label=label) for kind, label in holders(item)],
    )


@router.post("/{int:item_id}/placements", response=Whereabouts)
def put(request, item_id: int, body: PutIn):
    """Положить объект ещё в одно место (тот же объект, не копия)."""
    from filesystem.models import Volume

    filemanager.link(get_object_or_404(Volume, pk=body.volume), body.parent, item_id, body.name)
    return where(request, item_id)


@router.post("/{int:item_id}/detach")
def detach(request, item_id: int, body: DetachIn):
    """Своя копия объекта для одного места: дальше они правятся отдельно. Ответ: новый объект."""
    from filesystem.manager.filemanager import detach as split
    from filesystem.models import Placement

    placement = get_object_or_404(Placement, pk=body.placement, item_id=item_id)
    return {"id": split(placement, request.user).pk}


@router.delete("/{int:item_id}")
def delete(request, item_id: int):
    from filesystem.manager.filemanager import delete_item

    return {"placements": delete_item(_item(item_id))}


@router.get("/{int:item_id}/revisions/{int:revision_id}", response=RevisionOut)
def revision(request, item_id: int, revision_id: int):
    found = get_object_or_404(ItemRevision.objects.select_related("saved_by"), pk=revision_id, item_id=item_id)
    changes = history.compare(found, _item(item_id))
    return RevisionOut(
        id=found.pk, saved_at=found.saved_at, saved_by=found.saved_by.get_username() if found.saved_by_id else None, name=found.name,
        format=found.format, body=found.body, meta=found.meta, changes={name: list(value) for name, value in changes.items()},
    )


@router.post("/{int:item_id}/revisions/{int:revision_id}/restore", response=ItemOut)
def restore(request, item_id: int, revision_id: int):
    found = get_object_or_404(ItemRevision, pk=revision_id, item_id=item_id)
    history.restore(_item(item_id), found, request.user)
    return _out(_item(item_id), request.user)


class ToText(Schema):
    placement: int


class TextPlaced(Schema):
    volume: int
    placement: int


class TextBlockers(Schema):
    reasons: list[str]


@router.get("/{int:item_id}/text-blockers", response=TextBlockers)
def text_blockers(request, item_id: int):
    """Почему объект нельзя превратить в свой текст места (пусто: можно)."""
    from filesystem.manager.filemanager import text_blockers as blockers

    return {"reasons": blockers(_item(item_id))}


@router.post("/{int:item_id}/to-text", response=TextPlaced)
def to_text(request, item_id: int, body: ToText):
    """Объект, который лежит только здесь и ни с чем не связан, становится своим текстом места; история объекта пропадает."""
    from filesystem.manager.filemanager import to_text as convert
    from filesystem.models import Placement

    placement = convert(get_object_or_404(Placement, pk=body.placement, item_id=item_id))
    return TextPlaced(volume=placement.volume_id, placement=placement.pk)
