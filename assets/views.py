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

from .models import Asset
from .nextcloud import NextcloudClient
from .services import guess_content_type, resolve_viewer_type

logger = logging.getLogger(__name__)

STREAM_CHUNK_SIZE = 64 * 1024


@staff_member_required
def browse_nextcloud(request):
    path = request.GET.get(
        "path",
        "AETHER",
    )

    path = path.strip("/")

    if not path or (
        path != "AETHER"
        and not path.startswith("AETHER/")
    ):
        return JsonResponse(
            {"error": "Invalid path."},
            status=400,
        )

    client = NextcloudClient.from_settings()

    try:
        items = client.list(path)
    except Exception:
        logger.exception("Nextcloud browse failed: %s", path)
        return JsonResponse(
            {"error": "Nextcloud request failed."},
            status=502,
        )

    result = []

    if path != "AETHER":
        parent = path.rsplit(
            "/",
            1,
        )[0]

        result.append(
            {
                "file_id": None,
                "name": "..",
                "path": "/" + parent,
                "is_directory": True,
                "is_parent": True,
            }
        )

    for item in items:
        result.append(
            {
                "file_id": item.file_id,
                "name": item.filename,
                "path": item.path,
                "is_directory": item.is_directory,
                "is_parent": False,
            }
        )

    result.sort(
        key=lambda item: (
            not item["is_directory"],
            not item["is_parent"],
            item["name"].lower(),
        )
    )

    return JsonResponse(
        {
            "path": "/" + path,
            "items": result,
        }
    )


def asset_content(request, public_id):
    """Serve asset contents using its public UUID."""
    asset = get_object_or_404(Asset, public_id=public_id)
    return _serve_asset_file(request, asset)


def asset_viewer(request, public_id):
    """Render the viewer page for an asset.

    Имя и тип файла берутся из закэшированных метаданных ассета:
    Nextcloud опрашивается только если кэш ещё пуст.
    """
    asset = get_object_or_404(Asset, public_id=public_id)

    if not asset.filename:
        try:
            asset.refresh_metadata()
        except Exception as exc:
            raise Http404("Unable to locate asset file.") from exc
        asset.save(
            update_fields=[
                "filename",
                "content_type",
                "size",
                "updated_at",
            ]
        )

    viewer_type = resolve_viewer_type(
        asset,
        asset.filename,
        asset.content_type,
    )

    return render(
        request,
        f"assets/viewers/{viewer_type.lower()}.html",
        {
            "asset": asset,
            "filename": asset.filename,
            "content_type": asset.content_type,
            "viewer_type": viewer_type,
            "content_url": reverse(
                "asset_viewer:content",
                kwargs={"public_id": asset.public_id},
            ),
        },
    )


def _find_file(client, asset: Asset):
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


def _serve_asset_file(request, asset: Asset):
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
        asset.save(
            update_fields=[
                "filename",
                "content_type",
                "size",
                "updated_at",
            ]
        )

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
