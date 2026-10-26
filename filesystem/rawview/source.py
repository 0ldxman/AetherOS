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
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

READ_LIMIT = 8 * 1024 * 1024

WIKI_FORMAT = {"doc": "doc", "scan": "scan", "web": "snp", "rec": "rec"}


@dataclass
class Payload:
    kind: str = "none"                         # none | wiki | asset | map | app
    body: bytes = b""                          # текст (wiki, map) или готовые байты (asset, app)
    fmt: str | None = None                     # формат, который диктует источник (тип записи вики)
    meta: dict = field(default_factory=dict)
    locked: bool = False                       # доступа нет: тело подменяется шумом
    stamp: str = ""                            # что меняется вместе с источником (для кэша размера)
    size: int | None = None                    # размер источника, если он известен без чтения (ассет)


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
    return Payload(
        kind="wiki",
        body=document.body.encode(),
        fmt=WIKI_FORMAT.get(document.type, "doc"),
        locked=not document_state(document, keys).open,
        stamp=f"wiki:{document.pk}:{document.updated_at.isoformat()}",
        meta={
            "who": document.created_by.get_username() if document.created_by else "unknown",
            "when": (document.world_date or document.updated_at.date()).isoformat(),
            "ref": document.direct_link or document.title,
            "src": f"aether://{chain}{document.title}",
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
    return Payload(kind="map", body=json.dumps(data, ensure_ascii=False, indent=1).encode(), stamp=f"map:{scene.pk}:{scene.updated_at.isoformat()}" if hasattr(scene, "updated_at") else f"map:{scene.pk}")


def resolve_payload(machine_file, keys, reader=None):
    """Источник данных файла по его адресу содержимого."""
    url = (machine_file.url or "").strip().lstrip("/")
    if not url:
        return Payload()

    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]

    if parts[:1] == ["view"] and len(parts) >= 2:
        return _asset(parts[1], reader)
    if parts[:2] == ["apps", "wiki"]:
        return _wiki(parts[2:], keys) if len(parts) > 2 else Payload()
    if parts[:2] == ["apps", "map"]:
        return _map(parse_qs(parsed.query), keys)
    if parts[:1] == ["apps"]:
        return Payload(kind="app", stamp=f"app:{url}", meta={"path": url})
    return Payload()
