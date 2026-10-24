from __future__ import annotations

import logging  # DIAG
import time  # DIAG

import requests
from django.contrib.admin.views.decorators import (
    staff_member_required,
)
from django.http import (
    Http404,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import (
    content_disposition_header,
)

from .models import Asset
from .nextcloud import NextcloudClient
from .services import guess_content_type, resolve_viewer_type

logger = logging.getLogger(__name__)  # DIAG


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
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=500,
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


def asset_file(
    request,
    asset_id: int,
):
    """Legacy endpoint using the database primary key."""
    try:
        asset = Asset.objects.get(
            pk=asset_id,
        )
    except Asset.DoesNotExist:
        raise Http404(
            "Asset not found."
        )

    return _serve_asset_file(
        request,
        asset,
    )


def asset_content(
    request,
    public_id,
):
    """Serve asset contents using its public UUID."""
    try:
        asset = Asset.objects.get(
            public_id=public_id,
        )
    except Asset.DoesNotExist:
        raise Http404(
            "Asset not found."
        )

    return _serve_asset_file(
        request,
        asset,
    )


def asset_viewer(
    request,
    public_id,
):
    """Render the viewer page for an asset."""
    try:
        asset = Asset.objects.get(
            public_id=public_id,
        )
    except Asset.DoesNotExist:
        raise Http404(
            "Asset not found."
        )

    client = NextcloudClient.from_settings()

    try:
        file = client.get_file_by_id(
            asset.file_id,
        )
    except Exception as exc:
        raise Http404(
            "Unable to locate asset file."
        ) from exc

    if file is None or file.is_directory:
        raise Http404(
            "Asset file not found."
        )

    content_type = guess_content_type(file.filename)

    viewer_type = resolve_viewer_type(
        asset,
        file.filename,
        content_type,
    )

    template_name = f"assets/viewers/{viewer_type.lower()}.html"

    return render(
        request,
        template_name,
        {
            "asset": asset,
            "filename": file.filename,
            "content_type": content_type,
            "viewer_type": viewer_type,
            "content_url": reverse(
                "asset_viewer:content",
                kwargs={"public_id": asset.public_id},
            ),
        },
    )


def _serve_asset_file(
    request,
    asset: Asset,
):
    """Stream an asset from Nextcloud to the client."""
    if request.method not in {"GET", "HEAD"}:
        return HttpResponse(
            status=405,
            headers={"Allow": "GET, HEAD"},
        )

    client = NextcloudClient.from_settings()

    t0 = time.monotonic()  # DIAG: старт поиска файла

    try:
        file = client.get_file_by_id(asset.file_id)
    except Exception as exc:
        raise Http404(
            "Unable to locate asset file."
        ) from exc

    if file is None:
        raise Http404("Asset file not found.")

    if file.is_directory:
        raise Http404("Asset points to a directory.")

    t1 = time.monotonic()  # DIAG: поиск файла закончен

    content_type = guess_content_type(file.filename)

    etag = file.etag
    last_modified = file.last_modified

    if (
        etag
        and request.headers.get("If-None-Match") == etag
    ):
        response = HttpResponse(status=304)
        response["ETag"] = etag

        if last_modified:
            response["Last-Modified"] = last_modified

        return response

    if request.method == "HEAD":
        response = HttpResponse(
            status=200,
            content_type=content_type,
        )

        response["Content-Disposition"] = (
            content_disposition_header(
                False,
                file.filename,
            )
        )
        response["Accept-Ranges"] = "bytes"

        if etag:
            response["ETag"] = etag

        if last_modified:
            response["Last-Modified"] = last_modified

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
        raise Http404(
            "Unable to download asset."
        ) from exc

    t2 = time.monotonic()  # DIAG: Nextcloud начал отдавать ответ

    logger.warning(  # DIAG
        "asset %s: lookup %.2fs, stream-open %.2fs, range=%s",
        asset.public_id,
        t1 - t0,
        t2 - t1,
        range_header,
    )

    # Не передаём ошибки Nextcloud клиенту как успешный поток.
    if upstream.status_code not in (200, 206):
        try:
            upstream.raise_for_status()
            raise Http404("Unable to retrieve asset content.")
        except requests.RequestException as exc:
            raise Http404(
                "Unable to retrieve asset content."
            ) from exc
        finally:
            upstream.close()

    response = StreamingHttpResponse(
        _stream_upstream_response(upstream),
        status=upstream.status_code,
        content_type=content_type,
    )

    response["Content-Disposition"] = (
        content_disposition_header(
            False,
            file.filename,
        )
    )
    response["Accept-Ranges"] = "bytes"

    if etag:
        response["ETag"] = etag

    if last_modified:
        response["Last-Modified"] = last_modified

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


def _stream_upstream_response(
    response,
):
    try:
        for chunk in response.iter_content(
            chunk_size=64 * 1024,
        ):
            if chunk:
                yield chunk
    finally:
        response.close()