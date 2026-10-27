"""На что указывает файл: откуда брать настоящие данные для его байтов.

Адрес содержимого файла (MachineFile.url) ведёт:
    view/<uuid>/            в ассет: настоящие байты из Nextcloud;
    apps/wiki/...           в запись вики: её текст, тип и поля;
    apps/map/?scene=слаг    в сохранённую карту: её видимые игроку данные;
    apps/...                в другое приложение: короткий дескриптор;
    пусто                   никуда: шума нет смысла прятать, он просто шум.
Доступ учитывается: запись вики, закрытая от игрока по ключам, отдаёт вместо тела шум той же длины.
"""
import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

READ_LIMIT = 8 * 1024 * 1024


@dataclass
class Payload:
    kind: str = "none"                         # none | wiki | asset | map | mail | app | key | slice | archive
    body: bytes = b""                          # текст (wiki, map) или готовые байты (asset, app)
    fmt: str | None = None                     # формат, который диктует источник (тип записи вики)
    meta: dict = field(default_factory=dict)
    views: dict = field(default_factory=dict)  # тело в видах формата (flatten.STYLES): текст, html, объекты, ocr
    locked: bool = False                       # доступа нет: тело подменяется шумом
    stamp: str = ""                            # что меняется вместе с источником (для кэша размера)
    size: int | None = None                    # размер источника, если он известен без чтения (ассет)
    build: object = None                       # как получить тело лениво (архив: читать всех членов ради размера незачем)


def _wiki_document(parts):
    from wiki.models import Document, Namespace

    namespace = None
    for part in parts[:-1]:
        namespace = Namespace.objects.filter(parent=namespace, name=part).first()
        if namespace is None:
            return None
    return Document.objects.filter(namespace=namespace, title=parts[-1]).select_related("namespace", "created_by").first()


def _wiki(parts, keys):
    from wiki.access import document_state
    from wiki.models import Document

    if len(parts) == 2 and parts[0] == "go":
        document = Document.objects.filter(direct_link=parts[1]).select_related("namespace", "created_by").first()
    else:
        document = _wiki_document(parts)
    if document is None:
        return Payload()

    chain = document.namespace.path().replace(":", "/") + "/" if document.namespace else ""
    from filesystem.rawview import flatten
    from filesystem.rawview.registry import format_for_extension

    found = format_for_extension(document.EXTENSIONS.get(document.type, ".doc"))   # тип записи -> расширение -> формат
    return Payload(
        kind="wiki",
        body=document.body.encode(),
        views=flatten.views(document.body, keys),
        fmt=found.name if found else None,
        locked=not document_state(document, keys).open,
        stamp=f"wiki:{document.pk}:{document.updated_at.isoformat()}",
        meta={
            "who": document.created_by.get_username() if document.created_by else "unknown",
            "when": (document.world_date or document.updated_at.date()).isoformat(),
            "ref": document.direct_link or document.title,
            "src": f"wiki://{chain}{document.title}",
            "at": document.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "title": document.title,
        },
    )


def _asset(public_id, reader):
    import uuid

    from assets.models import Asset

    try:
        asset = Asset.objects.filter(public_id=uuid.UUID(public_id)).first()
    except ValueError:
        return Payload()
    if asset is None:
        return Payload()
    return Payload(kind="asset", body=b"", size=asset.size, stamp=f"asset:{asset.pk}:{asset.updated_at.isoformat()}",
                   meta={"asset": asset, "reader": reader})


def _map(query, keys):
    from map.models import MapScene
    from map.scenes import visible_features

    scene = MapScene.objects.filter(slug=(query.get("scene") or [""])[0]).first()
    if scene is None:
        return Payload()
    data = {
        "slug": scene.slug, "title": scene.title, "mode": scene.mode, "lat": scene.lat, "lon": scene.lon, "zoom": scene.zoom,
        "features": visible_features(scene.features, keys),
    }
    return Payload(kind="map", fmt="map", meta={"ref": scene.slug, "title": scene.title}, body=json.dumps(data, ensure_ascii=False, indent=1).encode(), stamp=f"map:{scene.pk}:{scene.updated_at.isoformat()}" if hasattr(scene, "updated_at") else f"map:{scene.pk}")


def _mail(parts, query, viewer):
    """Письмо по ?message=слаг или .../api/messages/<pk>/: текст с заголовками. Не доступное читателю закрыто шумом."""
    from mail.access import visible_messages
    from mail.models import Message

    ref = (query.get("message") or [""])[0]
    if not ref and len(parts) >= 4 and parts[-2].isdigit():
        ref = parts[-2]
    message = Message.objects.filter(slug=ref).first() or (Message.objects.filter(pk=int(ref)).first() if ref.isdigit() else None)
    if message is None:
        return Payload()

    seen = bool(viewer) and bool(visible_messages(viewer, pk=message.pk, attachments=False))
    return Payload(
        kind="mail",
        body=message.body.encode(),
        locked=not seen,
        stamp=f"mail:{message.pk}:{message.updated_at.isoformat()}",
        meta={
            "sender": message.sender,
            "recipients": ", ".join(line.strip() for line in message.recipients.splitlines() if line.strip()),
            "subject": message.subject,
            "date": message.sent_at.strftime("%a, %d %b %Y %H:%M:%S +0000"),
            "id": message.slug or str(message.pk),
        },
    )


def _key(slug):
    """Файл ключа в папке секретов игрока: блок ключа, как он лежит в байтах файлов."""
    from filesystem.rawview import keys

    return Payload(kind="key", body=keys.armor(slug, f"store:{slug}"), stamp=f"key:{slug}")


def _slice(machine_file, keys, reader, viewer):
    """Вырезка (blk): окно в байтах источника с тем прогрессом по слоям, какой был при вырезке."""
    from filesystem.models import FileSlice
    from filesystem.rawview.generate import build_raw

    cut = FileSlice.objects.filter(file=machine_file).select_related("source", "source__machine").first()
    if cut is None:
        return Payload()
    data = build_raw(cut.source, cut.state, keys, reader, viewer).data
    return Payload(
        kind="slice", body=data[cut.start:cut.end], stamp=f"slice:{cut.pk}:{cut.source.updated_at.timestamp()}",
    )


def _archive(machine_file, keys, reader, viewer):
    """Архив: заголовок pak, таблица (имя, размер, смещение) и данные членов. Данные члена это его собственные байты с его
    слоями, у вложенного архива это его архив целиком. Тело строится лениво: для размера и кэша хватает отпечатка."""
    from filesystem import archives
    from filesystem.rawview import formats
    from filesystem.rawview.generate import build_raw

    def build():
        found = [(name, build_raw(item, "", keys, reader, viewer).data) for name, item in archives.members(machine_file)]
        table, offset = b"", 0
        header = len(formats.magic("pak")) + 2 + sum(2 + len(name.encode()) + 8 for name, _ in found)
        for name, data in found:
            table += len(name.encode()).to_bytes(2, "big") + name.encode() + len(data).to_bytes(4, "big") + (header + offset).to_bytes(4, "big")
            offset += len(data)
        return formats.magic("pak") + len(found).to_bytes(2, "big") + table + b"".join(data for _, data in found)

    return Payload(kind="archive", build=build, stamp=f"archive:{machine_file.pk}:{archives.stamp(machine_file)}")


def resolve_payload(machine_file, keys, reader=None, viewer=None):
    """Источник данных файла по его адресу содержимого."""
    url = (machine_file.url or "").strip().lstrip("/")
    if not url:
        from filesystem import archives

        if archives.is_archive(machine_file):
            return _archive(machine_file, keys, reader, viewer)
        return Payload()

    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]

    if parts[:1] == ["keys"] and len(parts) == 2:
        return _key(parts[1])
    if parts == ["slice"]:
        return _slice(machine_file, keys, reader, viewer)

    if parts[:1] == ["view"] and len(parts) >= 2:
        return _asset(parts[1], reader)
    if parts[:2] == ["apps", "wiki"]:
        return _wiki(parts[2:], keys) if len(parts) > 2 else Payload()
    if parts[:2] == ["apps", "map"]:
        return _map(parse_qs(parsed.query), keys)
    if parts[:2] == ["apps", "mail"]:
        found = _mail(parts, parse_qs(parsed.query), viewer)
        return found if found.kind == "mail" else Payload(kind="app", stamp=f"app:{url}", meta={"path": url})
    if parts[:1] == ["apps"]:
        return Payload(kind="app", stamp=f"app:{url}", meta={"path": url})
    return Payload()
