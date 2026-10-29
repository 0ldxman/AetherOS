"""Байты файла как ответ на запрос вьювера: целиком или по Range (вьювер читает кусками)."""
import re

from django.http import HttpResponse

RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def serve(request, data):
    total = len(data)

    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store", "Content-Type": "application/octet-stream"}
    if request.method == "HEAD":
        response = HttpResponse(status=200, headers=headers)
        response["Content-Length"] = str(total)
        return response

    header = request.headers.get("Range")
    if not header:
        return HttpResponse(data, status=200, headers=headers)

    found = RANGE.match(header.strip())
    if not found or (found.group(1) == "" and found.group(2) == ""):
        return HttpResponse(status=416, headers={"Content-Range": f"bytes */{total}"})

    if found.group(1) == "":                                  # bytes=-N: последние N байт
        start, end = max(0, total - int(found.group(2))), total - 1
    else:
        start = int(found.group(1))
        end = min(int(found.group(2)), total - 1) if found.group(2) else total - 1

    if start >= total or start > end:
        return HttpResponse(status=416, headers={"Content-Range": f"bytes */{total}"})

    response = HttpResponse(data[start:end + 1], status=206, headers=headers)
    response["Content-Range"] = f"bytes {start}-{end}/{total}"
    return response
