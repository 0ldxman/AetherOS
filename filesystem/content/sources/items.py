"""Виды содержимого файла по тому, что лежит в его объекте (или у самого игрока)."""
import json

from filesystem.content.sources.base import Content, Payload, Source, site_url, text_window


def _meta(item):
    """Подстановки шаблонов формата: кто, когда, ссылка, откуда, название."""
    when = item.world_updated_at or item.world_created_at or item.updated_at.date()
    return {
        "who": item.world_creator or "unknown", "when": when.isoformat(), "ref": item.name, "src": f"file://{item.name}",
        "at": item.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"), "title": item.name,
    }


def _locked(entry, keys):
    from secure.access import satisfied

    return not all(satisfied(condition, keys) for condition in entry.conditions)


document_window = None  # (address) -> Content: окно документа для форматов с разметкой; ставит приложение документов


class OwnSource(Source):
    """Файл игрока без объекта: подпись (текст) или вырезка (байты)."""

    name = "own"

    def accepts(self, entry):
        return entry.item is None and entry.player is not None and (entry.player.content is not None or entry.player.data is not None)

    def payload(self, entry, view, keys, reader, viewer):
        body = entry.own_data if entry.own_data is not None else (entry.own_text or "").encode()
        return Payload(kind="own", layout="raw", body=body, stamp=f"own:{entry.player.pk}:{entry.player.updated_at.timestamp()}")

    def window(self, entry, address):
        return text_window(address) if entry.own_text is not None else Content(error="empty")


class ArchiveSource(Source):
    """Архив: заголовок pak, таблица (имя, размер, смещение) и данные членов. Данные члена это его собственные байты с его
    слоями, у вложенного архива это его архив целиком. Тело строится лениво: для размера и кэша хватает отпечатка."""

    name = "archive"

    def accepts(self, entry):
        return entry.archive

    def payload(self, entry, view, keys, reader, viewer):
        from filesystem.content import archives
        from filesystem.content.rawview import formats
        from filesystem.content.rawview.generate import build_raw

        members = archives.members(view, entry)

        def build():
            found = [(name, build_raw(member, view, keys, reader, viewer).data) for name, member in members]
            table, offset = b"", 0
            header = len(formats.magic("pak")) + 2 + sum(2 + len(name.encode()) + 8 for name, _ in found)
            for name, data in found:
                table += len(name.encode()).to_bytes(2, "big") + name.encode() + len(data).to_bytes(4, "big") + (header + offset).to_bytes(4, "big")
                offset += len(data)
            return formats.magic("pak") + len(found).to_bytes(2, "big") + table + b"".join(data for _, data in found)

        return Payload(kind="archive", layout="archive", real=True, build=build, stamp=f"archive:{entry.path}:{archives.stamp(members)}")


class AssetSource(Source):
    """Ассет: настоящие байты из Nextcloud."""

    name = "asset"

    def accepts(self, entry):
        return entry.item is not None and entry.item.asset_id is not None

    def payload(self, entry, view, keys, reader, viewer):
        asset = entry.item.asset
        return Payload(kind="asset", layout="asset", real=True, size=asset.size, stamp=f"asset:{asset.pk}:{asset.updated_at.isoformat()}",
                       meta={"asset": asset, "reader": reader})

    def window(self, entry, address):
        from django.urls import reverse

        return Content(url=reverse("asset_viewer:viewer", kwargs={"public_id": entry.item.asset.public_id}))


class LinkSource(Source):
    """Внешняя ссылка: окно показывает адрес, а байты файла генерируются (с сети ничего не качается)."""

    name = "link"

    def accepts(self, entry):
        return entry.item is not None and bool(entry.item.url)

    def payload(self, entry, view, keys, reader, viewer):
        return Payload(kind="link", layout="noise", stamp=f"link:{entry.item.pk}:{entry.item.updated_at.isoformat()}")

    def window(self, entry, address):
        return Content(url=entry.item.url)


class SceneSource(Source):
    """Сохранённая карта: её видимые игроку данные."""

    name = "map"

    def accepts(self, entry):
        return entry.item is not None and entry.item.scene_id is not None

    def payload(self, entry, view, keys, reader, viewer):
        from map.scenes import visible_features

        scene = entry.item.scene
        data = {
            "slug": scene.slug, "title": scene.title, "mode": scene.mode, "lat": scene.lat, "lon": scene.lon, "zoom": scene.zoom,
            "features": visible_features(scene.features, keys),
        }
        return Payload(
            kind="map", layout="format", default_fmt="map", fmt="map", meta={"ref": scene.slug, "title": scene.title},
            body=json.dumps(data, ensure_ascii=False, indent=1).encode(),
            stamp=f"map:{scene.pk}:{scene.updated_at.isoformat()}" if hasattr(scene, "updated_at") else f"map:{scene.pk}",
        )

    def window(self, entry, address):
        return Content(url=site_url(f"apps/map/?scene={entry.item.scene.slug}"))


class MessageSource(Source):
    """Письмо: текст с заголовками. Не доступное читателю закрыто шумом."""

    name = "mail"

    def accepts(self, entry):
        return entry.item is not None and entry.item.message_id is not None

    def payload(self, entry, view, keys, reader, viewer):
        from mail.access import visible_messages

        message = entry.item.message
        seen = bool(viewer) and bool(visible_messages(viewer, pk=message.pk, attachments=False))
        return Payload(
            kind="mail", layout="format", default_fmt="msg", body=message.body.encode(), locked=not seen,
            stamp=f"mail:{message.pk}:{message.updated_at.isoformat()}",
            meta={
                "sender": message.sender,
                "recipients": ", ".join(line.strip() for line in message.recipients.splitlines() if line.strip()),
                "subject": message.subject,
                "date": message.sent_at.strftime("%a, %d %b %Y %H:%M:%S +0000"),
                "id": message.slug or str(message.pk),
            },
        )

    def window(self, entry, address):
        message = entry.item.message
        return Content(url=site_url(f"apps/mail/?message={message.slug or message.pk}"))


class KeySource(Source):
    """Ключ: его текст, а если текста нет, блок, который система строит из слага."""

    name = "key"

    def accepts(self, entry):
        from filesystem.models import KEY_FORMAT

        return entry.item is not None and entry.item.format == KEY_FORMAT

    def payload(self, entry, view, keys, reader, viewer):
        from filesystem.content.rawview import keys as blocks

        item = entry.item
        body = entry.body.encode() if entry.body.strip() else blocks.armor(item.slug, f"store:{item.slug}")
        return Payload(kind="key", layout="raw", body=body, stamp=f"key:{item.pk}:{item.updated_at.isoformat()}:{hash(body)}")

    def window(self, entry, address):
        return text_window(address)


def _text_payload(entry, body, fmt, stamp, meta, keys):
    """Текст в контейнере своего формата (если формат известен), с видами разметки для документов; иначе как есть."""
    from filesystem.content.rawview import flatten, formats, registry

    found = registry.format_named(fmt) if fmt else None
    if found is None or not formats.known(found.name):
        return Payload(kind="text", layout="raw", body=body.encode(), locked=_locked(entry, keys), stamp=stamp)
    views = flatten.views(body, keys) if found.markup else {}
    return Payload(
        kind="text", layout="format", fmt=found.name, default_fmt=found.name, body=body.encode(), views=views, meta=meta,
        locked=_locked(entry, keys), stamp=stamp,
    )


def _text_window(entry, address):
    from filesystem.content.rawview import registry

    found = registry.format_named(entry.format) if entry.format else None
    if found is not None and found.markup and document_window is not None:
        return document_window(address)
    return text_window(address)


class TextSource(Source):
    """Текст объекта (с правкой игрока): в контейнере своего формата, если формат известен, иначе как есть."""

    name = "text"

    def accepts(self, entry):
        return entry.item is not None and bool(entry.body.strip())

    def payload(self, entry, view, keys, reader, viewer):
        item = entry.item
        body = entry.body
        return _text_payload(entry, body, item.format, f"text:{item.pk}:{item.updated_at.isoformat()}:{hash(body)}", _meta(item), keys)

    def window(self, entry, address):
        return _text_window(entry, address)


class AuthoredSource(Source):
    """Файл со своим текстом автора (размещение-файл или член архива), с правкой игрока поверх: как текстовый объект, но без него.

    Формат по расширению имени; подстановки шаблона формата берутся из имени и места."""

    name = "authored"

    def accepts(self, entry):
        return entry.authored and entry.own_data is None

    def payload(self, entry, view, keys, reader, viewer):
        body = entry.own_text or ""
        where = entry.placement.pk if entry.placement is not None else entry.path
        meta = {"who": "unknown", "when": "", "ref": entry.name, "src": f"file://{entry.name}", "at": "", "title": entry.name}
        return _text_payload(entry, body, entry.format, f"authored:{where}:{hash(body)}", meta, keys)

    def window(self, entry, address):
        return _text_window(entry, address)


class BlankSource(Source):
    """Файл без содержимого: байты выдуманы (шум нужного размера), всегда одни и те же."""

    name = "blank"

    def accepts(self, entry):
        return True

    def payload(self, entry, view, keys, reader, viewer):
        stamp = f"blank:{entry.item.pk}:{entry.item.updated_at.isoformat()}" if entry.item is not None else f"blank:{entry.path}"
        return Payload(kind="none", layout="noise", locked=False, stamp=stamp)

    def window(self, entry, address):
        return Content(error="empty")
