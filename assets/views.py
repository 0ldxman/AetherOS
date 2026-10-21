from __future__ import annotations

from mimetypes import guess_type

from django.contrib.admin.views.decorators import (
    staff_member_required,
)
from django.http import (
    Http404,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.utils.http import (
    content_disposition_header,
)

from .models import Asset
from .nextcloud import NextcloudClient


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
    try:
        asset = Asset.objects.get(
            pk=asset_id,
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

    if file is None:
        raise Http404(
            "Asset file not found."
        )

    if file.is_directory:
        raise Http404(
            "Asset points to a directory."
        )

    content_type, _ = guess_type(
        file.filename,
    )

    if content_type is None:
        content_type = (
            "application/octet-stream"
        )

    etag = file.etag
    last_modified = file.last_modified

    if (
        etag
        and request.headers.get(
            "If-None-Match"
        ) == etag
    ):
        response = HttpResponse(
            status=304,
        )

        response["ETag"] = etag

        if last_modified:
            response["Last-Modified"] = (
                last_modified
            )

        return response

    if request.method == "HEAD":
        response = HttpResponse(
            status=200,
            content_type=content_type,
        )

        response[
            "Content-Disposition"
        ] = content_disposition_header(
            False,
            file.filename,
        )

        response[
            "Accept-Ranges"
        ] = "bytes"

        if etag:
            response["ETag"] = etag

        if last_modified:
            response[
                "Last-Modified"
            ] = last_modified

        if file.size is not None:
            response[
                "Content-Length"
            ] = str(file.size)

        return response

    request_headers = {}

    range_header = request.headers.get(
        "Range"
    )

    if range_header:
        request_headers["Range"] = (
            range_header
        )

    try:
        upstream = client.stream(
            file.path,
            headers=request_headers,
        )
    except Exception as exc:
        raise Http404(
            "Unable to download asset."
        ) from exc

    response = StreamingHttpResponse(
        _stream_upstream_response(
            upstream
        ),
        status=upstream.status_code,
        content_type=content_type,
    )

    response[
        "Content-Disposition"
    ] = content_disposition_header(
        False,
        file.filename,
    )

    response[
        "Accept-Ranges"
    ] = "bytes"

    if etag:
        response["ETag"] = etag

    if last_modified:
        response[
            "Last-Modified"
        ] = last_modified

    content_length = (
        upstream.headers.get(
            "Content-Length"
        )
    )

    if content_length:
        response[
            "Content-Length"
        ] = content_length

    content_range = (
        upstream.headers.get(
            "Content-Range"
        )
    )

    if content_range:
        response[
            "Content-Range"
        ] = content_range

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