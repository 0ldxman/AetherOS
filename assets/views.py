from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import (
    staff_member_required,
)
from django.http import (
    Http404,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import content_disposition_header

from filesystem.content.locate import address_of, query
from filesystem.content.rawview import viewer_formats

from assets.nextcloud import NextcloudClient
from assets.services import asset_ref, asset_viewer_type, guess_content_type, list_folder

logger = logging.getLogger(__name__)

STREAM_CHUNK_SIZE = 64 * 1024


@staff_member_required
def browse_nextcloud(request):
    try:
        return JsonResponse(list_folder(request.GET.get("path", "AETHER")))
    except ValueError:
        return JsonResponse({"error": "Invalid path."}, status=400)
    except RuntimeError:
        return JsonResponse({"error": "Nextcloud request failed."}, status=502)


def _asset_item(request, public_id):
    """Объект с файлом по публичному адресу.

    Открытый из файлов игрока или раздела вики (?path=, ?wiki=, filesystem.content.locate) файл проверяется как место:
    условия папок и места (оно может заменить условие объекта или снять его) и слои с прогрессом игрока, как у cnt.
    По голой ссылке (картинка в документе) действует условие самого объекта. Без нужных ключей 403.
    """
    from django.core.exceptions import PermissionDenied

    from filesystem.content.locate import address_of, locate
    from filesystem.content.window import layers_block
    from filesystem.models import Item
    from secure.access import satisfied
    from secure.requestkeys import request_keys

    item = get_object_or_404(Item.objects.exclude(file_id=""), public_id=public_id)
    if request.user.is_staff:
        return item
    keys = request_keys(request)
    if address_of(request):
        entry, _ = locate(request)
        if entry.item is None or entry.item.pk != item.pk:
            raise Http404
        if layers_block(entry) or not all(satisfied(condition, keys) for condition in entry.conditions):
            raise PermissionDenied
        return item
    if item.access and not satisfied(item.access, keys):
        raise PermissionDenied
    return item


def asset_content(request, public_id):
    """Байты файла по публичному адресу объекта."""
    return _serve_asset_file(request, _asset_item(request, public_id))


def asset_viewer(request, public_id):
    """Страница просмотра файла объекта.

    Имя и тип файла берутся из кэша объекта: Nextcloud опрашивается только если кэш ещё пуст.
    """
    item = _asset_item(request, public_id)

    if not item.file_name:
        try:
            item.refresh_file()
        except Exception as exc:
            raise Http404("Unable to locate asset file.") from exc
        item.save(update_fields=["file_name", "file_type", "file_size"])

    viewer_type = asset_viewer_type(item)

    return render(
        request,
        f"assets/viewers/{viewer_type.lower()}.html",
        {
            "asset": asset_ref(item),
            "filename": item.file_name,
            "content_type": item.file_type,
            "viewer_type": viewer_type,
            "content_url": reverse("asset_viewer:content", kwargs={"public_id": item.public_id}) + "?" + query(address_of(request), v=item.file_id),
            "formats_json": viewer_formats(),
        },
    )


def _find_file(client, asset):
    """Файл ассета в Nextcloud или Http404."""
    try:
        file = client.get_file_by_id(asset.file_id)
    except Exception as exc:
        raise Http404("Unable to locate asset file.") from exc

    if file is None or file.is_directory:
        raise Http404("Asset file not found.")
    return file


def _apply_file_headers(response, file, content_type=None, as_attachment=False):
    """Заголовки, общие для GET, HEAD и 304. as_attachment: браузер сохраняет файл, а не показывает."""
    if content_type is not None:
        response["Content-Disposition"] = content_disposition_header(
            as_attachment,
            file.filename,
        )
    response["Accept-Ranges"] = "bytes"
    if file.etag:
        response["ETag"] = file.etag
    if file.last_modified:
        response["Last-Modified"] = file.last_modified
    return response


def _serve_asset_file(request, asset):
    """Stream an asset from Nextcloud to the client."""
    if request.method not in {"GET", "HEAD"}:
        return HttpResponse(
            status=405,
            headers={"Allow": "GET, HEAD"},
        )

    client = NextcloudClient.from_settings()
    file = _find_file(client, asset)
    content_type = guess_content_type(file.filename)

    # Файл уже получен из Nextcloud, поэтому заодно держим кэш метаданных
    # актуальным (переименование, подмена файла). Пишем только при изменении.
    if asset.apply_file(file):
        asset.save(update_fields=["file_name", "file_type", "file_size"])

    if (
        file.etag
        and request.headers.get("If-None-Match") == file.etag
    ):
        return _apply_file_headers(HttpResponse(status=304), file)

    if request.method == "HEAD":
        response = _apply_file_headers(
            HttpResponse(status=200, content_type=content_type),
            file,
            content_type,
        )
        if file.size is not None:
            response["Content-Length"] = str(file.size)
        return response

    request_headers = {}
    range_header = request.headers.get("Range")
    if range_header:
        request_headers["Range"] = range_header

    try:
        upstream = client.stream(
            file.path,
            headers=request_headers,
        )
    except Exception as exc:
        raise Http404("Unable to download asset.") from exc

    # Не передаём ошибки Nextcloud клиенту как успешный поток.
    if upstream.status_code not in (200, 206):
        upstream.close()
        raise Http404("Unable to retrieve asset content.")

    response = _apply_file_headers(
        StreamingHttpResponse(
            _stream_upstream_response(upstream),
            status=upstream.status_code,
            content_type=content_type,
        ),
        file,
        content_type,
        as_attachment=request.GET.get("download") == "1",
    )

    # requests.iter_content() автоматически распаковывает
    # gzip/deflate. Поэтому исходные заголовки длины и
    # кодирования нельзя безусловно передавать браузеру.
    content_encoding = upstream.headers.get(
        "Content-Encoding",
        "",
    ).strip().lower()

    if content_encoding not in {"gzip", "deflate", "br"}:
        content_length = upstream.headers.get("Content-Length")
        if content_length:
            response["Content-Length"] = content_length

    content_range = upstream.headers.get("Content-Range")
    if content_range:
        response["Content-Range"] = content_range

    return response


def _stream_upstream_response(response):
    try:
        for chunk in response.iter_content(
            chunk_size=STREAM_CHUNK_SIZE,
        ):
            if chunk:
                yield chunk
    finally:
        response.close()
