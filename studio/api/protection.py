"""Защита объекта (условие по ключам и слои), ключи и подписи, содержимое из других приложений (ассет, сцена, письмо, ссылка).

Всё, что игрок получит, считает код игры: слои разбирает filesystem.layers, байты строит filesystem.content.rawview, условие
secure.access. Здесь только схемы и проверки. Предпросмотр байтов не сохраняет ничего: он показывает, что увидит игрок в blk и txtx
со слоями и без них.
"""
import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from assets.services import asset_viewer_type, asset_widget_kind
from documents.markup.expr import SpoilerSyntaxError, parse_expr
from filesystem.content.rawview import build_raw
from filesystem.layers.compiler import StateError, compile_text
from filesystem.machine_view.entries import FILE, Entry
from filesystem.models import KEY_FORMAT, Item, ItemKey, ItemSignature
from mail.models import Message
from map.models import MapScene
from secure.access import condition_slugs, format_condition
from secure.keys import key_slugs
from secure.usage import key_usage

router = Router(tags=["protection"])

HEAD_BYTES = 256
ROW = 16


class Problem(Schema):
    line: int
    message: str


class Layer(Schema):
    line: int
    name: str
    params: dict[str, str]


class Dump(Schema):
    size: int
    format: str | None
    rows: list[dict]            # {offset, hex, ascii}
    printable: int              # доля печатных символов в начале, %


class ProtectionIn(Schema):
    access: str = ""
    state: str = ""


class Preview(Schema):
    layers: list[Layer]
    problems: list[Problem]
    access_error: str
    keys: list[str]             # слаги из условия
    unknown_keys: list[str]     # которых нет в реестре ключей
    plain: Dump | None          # байты без слоёв
    layered: Dump | None        # с теми слоями, что в тексте


class ProtectionOut(Schema):
    access: str
    state: str
    version: str


class SaveIn(Schema):
    access: str = ""
    state: str = ""
    version: str
    force: bool = False


class KeyRef(Schema):
    slug: str
    name: str


class Signature(Schema):
    slug: str
    name: str
    valid: bool
    date: dt.date | None


class Usage(Schema):
    kind: str
    label: str
    url: str


class KeysOut(Schema):
    embedded: list[KeyRef]
    signatures: list[Signature]
    is_key: bool
    required_by: list[Usage]    # только у объекта-ключа: где его требуют
    registry: list[KeyRef]


class SignatureIn(Schema):
    slug: str
    valid: bool = True
    date: dt.date | None = None


class KeysIn(Schema):
    embedded: list[str] = []
    signatures: list[SignatureIn] = []


class PickRef(Schema):
    id: int
    label: str
    sub: str = ""
    kind: str = ""


class FilePick(Schema):
    file_id: str                # ID файла в Nextcloud
    label: str                  # имя файла
    kind: str = ""              # audio | video | image | file: каким виджетом покажет вики
    view: str = ""              # как показывать: пусто (по типу файла) | audio | video | image | pdf | text | raw
    size: int | None = None
    shown: str = ""             # как файл показывается сейчас: audio | video | image | pdf | text | raw


class NextcloudEntry(Schema):
    file_id: str | None
    name: str
    path: str
    is_directory: bool
    is_parent: bool
    size: int | None = None
    kind: str = ""               # audio | video | image | pdf | text | raw (у папок пусто)


class NextcloudFolder(Schema):
    path: str
    items: list[NextcloudEntry]


class ContentOut(Schema):
    kind: str                   # text | asset | link | scene | message
    asset: FilePick | None
    scene: PickRef | None
    message: PickRef | None
    url: str


class ContentIn(Schema):
    kind: str
    file_id: str = ""
    view: str = ""
    scene: int | None = None
    message: int | None = None
    url: str = ""


def _item(item_id):
    return get_object_or_404(Item, pk=item_id)


def _expression(text):
    """Выражение условия -> условие secure.access или None (пусто = открыто). SpoilerSyntaxError, если не разобрать."""
    return parse_expr(text) if text.strip() else None


def _dump(data, fmt):
    head = data[:HEAD_BYTES]
    rows = [
        {"offset": f"{start:04x}", "hex": " ".join(f"{b:02x}" for b in head[start:start + ROW]),
         "ascii": "".join(chr(b) if 32 <= b < 127 else "·" for b in head[start:start + ROW])}
        for start in range(0, len(head), ROW)
    ]
    printable = round(100 * sum(1 for b in head if 32 <= b < 127 or b in (9, 10, 13)) / len(head)) if head else 0
    return Dump(size=len(data), format=fmt, rows=rows, printable=printable)


def entry_dump(entry):
    """Байты записи так, как их строит игра: без игрока, ключей и прогресса по слоям (слои стоят в полной силе)."""
    try:
        raw = build_raw(entry, keys=frozenset())
    except Exception:                                   # предпросмотр не должен ронять студию
        return None
    return _dump(raw.data, raw.format)


def _bytes(item, state):
    original = item.state
    item.state = state
    try:
        return entry_dump(Entry(path=f"/{item.name}", kind=FILE, item=item))
    finally:
        item.state = original


def check_protection(state, access):
    """(слои, проблемы слоёв, ошибка условия, ключи условия, неизвестные ключи) для текста слоёв и выражения условия."""
    layers, problems = [], []
    try:
        for compiled in compile_text(state) if state.strip() else []:
            layers.append(Layer(line=compiled.layer.line, name=compiled.state.name,
                                params={key: str(value) for key, value in compiled.params.items() if value is not None}))
    except StateError as exc:
        problems = [Problem(line=p.line, message=p.message) for p in exc.problems]
    access_error, slugs = "", []
    try:
        slugs = sorted(condition_slugs(_expression(access)))
    except SpoilerSyntaxError as exc:
        access_error = str(exc)
    known = set(key_slugs())
    return layers, problems, access_error, slugs, [slug for slug in slugs if slug not in known]


@router.post("/{int:item_id}/protection/preview", response=Preview)
def preview(request, item_id: int, body: ProtectionIn):
    item = _item(item_id)
    layers, problems, access_error, slugs, unknown = check_protection(body.state, body.access)
    return Preview(
        layers=layers, problems=problems, access_error=access_error, keys=slugs, unknown_keys=unknown,
        plain=_bytes(item, ""), layered=_bytes(item, body.state) if body.state.strip() and not problems else None,
    )


@router.get("/{int:item_id}/protection", response=ProtectionOut)
def protection(request, item_id: int):
    item = _item(item_id)
    return ProtectionOut(access=format_condition(item.access) if item.access else "", state=item.state, version=item.updated_at.isoformat())


@router.put("/{int:item_id}/protection", response={200: ProtectionOut, 409: dict})
def save_protection(request, item_id: int, body: SaveIn):
    item = _item(item_id)
    if item.updated_at.isoformat() != body.version and not body.force:
        return 409, {"detail": "Объект изменён после того, как вы его открыли.", "version": item.updated_at.isoformat(),
                     "by": item.updated_by.get_username() if item.updated_by_id else None}
    errors = {}
    try:
        item.access = _expression(body.access) or {}
    except SpoilerSyntaxError as exc:
        errors["access"] = [str(exc)]
    item.state = body.state
    item.updated_by = request.user
    try:
        item.full_clean()
    except ValidationError as exc:
        errors.update(exc.message_dict)
    if errors:
        raise ValidationError(errors)
    item.save()
    return protection(request, item_id)


# ---- ключи и подписи -----------------------------------------------------------------------------------------------

def _keys(item):
    return KeysOut(
        embedded=[KeyRef(slug=link.key.slug, name=link.key.name) for link in item.keys.select_related("key").order_by("key__slug")],
        signatures=[Signature(slug=s.key.slug, name=s.key.name, valid=s.valid, date=s.date) for s in item.signatures.select_related("key").order_by("key__slug")],
        is_key=item.format == KEY_FORMAT,
        required_by=[Usage(kind=u.kind, label=u.label, url=u.url) for u in key_usage(item.slug)] if item.format == KEY_FORMAT else [],
        registry=[KeyRef(slug=k.slug, name=k.name) for k in Item.objects.filter(format=KEY_FORMAT).order_by("slug")],
    )


@router.get("/{int:item_id}/keys", response=KeysOut)
def keys(request, item_id: int):
    return _keys(_item(item_id))


@router.put("/{int:item_id}/keys", response=KeysOut)
@transaction.atomic
def save_keys(request, item_id: int, body: KeysIn):
    """Встроенные ключи (их достаёт kex) и подписи (ward verify) целиком. Ключи берутся только из реестра."""
    item = _item(item_id)
    wanted = {*body.embedded, *(s.slug for s in body.signatures)}
    found = {k.slug: k for k in Item.objects.filter(format=KEY_FORMAT, slug__in=wanted)}
    missing = sorted(wanted - set(found))
    if missing:
        raise ValidationError({"embedded": [f"Нет таких ключей в реестре: {', '.join(missing)}."]})
    item.keys.exclude(key__slug__in=body.embedded).delete()
    for slug in body.embedded:
        ItemKey.objects.get_or_create(item=item, key=found[slug])
    item.signatures.exclude(key__slug__in=[s.slug for s in body.signatures]).delete()
    for sign in body.signatures:
        ItemSignature.objects.update_or_create(item=item, key=found[sign.slug], defaults={"valid": sign.valid, "date": sign.date})
    return _keys(item)


# ---- содержимое из других приложений ---------------------------------------------------------------------------------

def _content(item):
    kind = "asset" if item.file_id else "scene" if item.scene_id else "message" if item.message_id else "link" if item.url else "text"
    return ContentOut(
        kind=kind,
        asset=FilePick(file_id=item.file_id, label=item.file_name or item.file_id, kind=asset_widget_kind(item), view=item.file_view, size=item.file_size, shown=asset_viewer_type(item).lower()) if item.file_id else None,
        scene=PickRef(id=item.scene_id, label=item.scene.title, sub=item.scene.slug) if item.scene_id else None,
        message=PickRef(id=item.message_id, label=item.message.subject or "(без темы)", sub=item.message.sender) if item.message_id else None,
        url=item.url,
    )


@router.get("/{int:item_id}/content", response=ContentOut)
def content(request, item_id: int):
    return _content(Item.objects.select_related("scene", "message").get(pk=item_id))


@router.put("/{int:item_id}/content", response=ContentOut)
def set_content(request, item_id: int, body: ContentIn):
    """Откуда берётся содержимое: текст, ассет, ссылка, сцена карты или письмо. Остальные источники сбрасываются; текст при
    смене на другой источник не стирается молча: сначала автор очищает его сам."""
    item = Item.objects.select_related("scene", "message").get(pk=item_id)
    if body.kind not in ("text", "asset", "link", "scene", "message"):
        raise ValidationError({"kind": ["Неизвестный источник."]})
    if body.kind != "text" and item.body.strip():
        raise ValidationError({"__all__": ["У объекта есть текст: очистите его на вкладке «Содержимое», потом выбирайте источник."]})
    same = body.kind == "asset" and body.file_id.strip() == item.file_id
    cached = (item.file_name, item.file_type, item.file_size)
    item.file_id, item.file_name, item.file_type, item.file_size, item.file_view = "", "", "", None, ""
    if body.kind == "asset" and body.file_id.strip():
        item.file_id = body.file_id.strip()
        item.file_view = body.view
        if same:                                                      # тот же файл: меняется только вид, в Nextcloud не ходим
            item.file_name, item.file_type, item.file_size = cached
        else:
            try:
                item.refresh_file()
            except Exception:
                raise ValidationError({"__all__": ["Такого файла нет в Nextcloud или хранилище не отвечает."]})
    item.scene = get_object_or_404(MapScene, pk=body.scene) if body.kind == "scene" and body.scene else None
    item.message = get_object_or_404(Message, pk=body.message) if body.kind == "message" and body.message else None
    item.url = body.url.strip() if body.kind == "link" else ""
    item.updated_by = request.user
    item.full_clean()
    item.save()
    return _content(item)


@router.get("/nextcloud", response=NextcloudFolder)
def nextcloud(request, path: str = "AETHER"):
    """Папка хранилища (Nextcloud) для выбора файла объекта: только внутри AETHER."""
    from assets.services import list_folder

    try:
        return list_folder(path)
    except ValueError:
        raise ValidationError({"__all__": ["Папка вне хранилища AETHER."]})
    except RuntimeError:
        raise ValidationError({"__all__": ["Хранилище не отвечает."]})


@router.get("/pick/scenes", response=list[PickRef])
def pick_scenes(request, q: str = ""):
    found = MapScene.objects.order_by("title")
    if q.strip():
        found = found.filter(Q(title__icontains=q.strip()) | Q(slug__icontains=q.strip()))
    return [PickRef(id=s.pk, label=s.title, sub=s.slug) for s in found[:30]]


@router.get("/pick/messages", response=list[PickRef])
def pick_messages(request, q: str = ""):
    found = Message.objects.order_by("-pk")
    if q.strip():
        found = found.filter(Q(subject__icontains=q.strip()) | Q(sender__icontains=q.strip()) | Q(slug__icontains=q.strip()))
    return [PickRef(id=m.pk, label=m.subject or "(без темы)", sub=m.sender) for m in found[:30]]


