"""Источники, которые лежат в приложениях сайта: ассет, запись вики, карта, письмо и приложение как таковое."""
import json

from filesystem.sources.base import Payload, Source


class AssetSource(Source):
    """view/<uuid>/ в ассет: настоящие байты из Nextcloud."""

    name = "asset"

    def accepts(self, address):
        return address.parts[:1] == ["view"] and len(address.parts) >= 2

    def payload(self, machine_file, address, keys, reader, viewer):
        import uuid

        from assets.models import Asset

        try:
            asset = Asset.objects.filter(public_id=uuid.UUID(address.parts[1])).first()
        except ValueError:
            return Payload()
        if asset is None:
            return Payload()
        return Payload(kind="asset", layout="asset", real=True, body=b"", size=asset.size, stamp=f"asset:{asset.pk}:{asset.updated_at.isoformat()}",
                       meta={"asset": asset, "reader": reader})


def _wiki_document(parts):
    from wiki.models import Document, Namespace

    namespace = None
    for part in parts[:-1]:
        namespace = Namespace.objects.filter(parent=namespace, name=part).first()
        if namespace is None:
            return None
    return Document.objects.filter(namespace=namespace, title=parts[-1]).select_related("namespace", "created_by").first()


class WikiSource(Source):
    """apps/wiki/...: запись вики, её текст, тип и поля."""

    name = "wiki"

    def accepts(self, address):
        return address.parts[:2] == ["apps", "wiki"]

    def payload(self, machine_file, address, keys, reader, viewer):
        parts = address.parts[2:]
        if not parts:
            return Payload()

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
            layout="format",
            default_fmt="rec",
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


class MapSource(Source):
    """apps/map/?scene=слаг: сохранённая карта, её видимые игроку данные."""

    name = "map"

    def accepts(self, address):
        return address.parts[:2] == ["apps", "map"]

    def payload(self, machine_file, address, keys, reader, viewer):
        from map.models import MapScene
        from map.scenes import visible_features

        scene = MapScene.objects.filter(slug=(address.query.get("scene") or [""])[0]).first()
        if scene is None:
            return Payload()
        data = {
            "slug": scene.slug, "title": scene.title, "mode": scene.mode, "lat": scene.lat, "lon": scene.lon, "zoom": scene.zoom,
            "features": visible_features(scene.features, keys),
        }
        return Payload(
            kind="map", layout="format", default_fmt="map", fmt="map", meta={"ref": scene.slug, "title": scene.title},
            body=json.dumps(data, ensure_ascii=False, indent=1).encode(),
            stamp=f"map:{scene.pk}:{scene.updated_at.isoformat()}" if hasattr(scene, "updated_at") else f"map:{scene.pk}",
        )


class AppSource(Source):
    """apps/...: другое приложение, короткий дескриптор."""

    name = "app"

    def accepts(self, address):
        return address.parts[:1] == ["apps"]

    def payload(self, machine_file, address, keys, reader, viewer):
        return Payload(kind="app", layout="app", stamp=f"app:{address.url}", meta={"path": address.url})


class MailSource(Source):
    """apps/mail/?message=слаг: письмо текстом с заголовками. Не доступное читателю закрыто шумом."""

    name = "mail"

    def accepts(self, address):
        return address.parts[:2] == ["apps", "mail"]

    def payload(self, machine_file, address, keys, reader, viewer):
        from mail.access import visible_messages
        from mail.models import Message

        parts = address.parts
        ref = (address.query.get("message") or [""])[0]
        if not ref and len(parts) >= 4 and parts[-2].isdigit():
            ref = parts[-2]
        message = Message.objects.filter(slug=ref).first() or (Message.objects.filter(pk=int(ref)).first() if ref.isdigit() else None)
        if message is None:
            return AppSource().payload(machine_file, address, keys, reader, viewer)         # письма нет: приложение как таковое

        seen = bool(viewer) and bool(visible_messages(viewer, pk=message.pk, attachments=False))
        return Payload(
            kind="mail",
            layout="format",
            default_fmt="msg",
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
