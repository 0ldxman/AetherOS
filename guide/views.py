from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404

from guide import pages


@staff_member_required
def media(request, name):
    """Картинка или видео справки: только автору Студии, только из docs/guide/media."""
    path = pages.media_path(name)
    if path is None:
        raise Http404
    response = FileResponse(path.open("rb"), content_type="image/png" if name.endswith(".png") else "video/webm")
    response["Cache-Control"] = "no-cache"
    return response
