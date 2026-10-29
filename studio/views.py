"""Страница студии: оболочка, в которую Vite собрал приложение (studio/frontend -> studio/static/studio/app).

Файлы сборки называются с хешем; какие подключать, говорит манифест Vite. Без сборки страница говорит, как её собрать.
"""
import json
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

BUILD = Path(__file__).resolve().parent / "static" / "studio" / "app"
ENTRY = "src/main.ts"


def _assets():
    """(скрипт, [стили]) входной точки из манифеста сборки или None, если фронт ещё не собран."""
    try:
        manifest = json.loads((BUILD / ".vite" / "manifest.json").read_text())
    except (OSError, ValueError):
        return None
    entry = manifest.get(ENTRY)
    if entry is None:
        return None
    return "studio/app/" + entry["file"], ["studio/app/" + css for css in entry.get("css", [])]


@staff_member_required
@ensure_csrf_cookie                    # API пишет с CSRF-токеном из куки
def shell(request):
    found = _assets()
    return render(request, "studio/index.html", {
        "script": found[0] if found else None,
        "styles": found[1] if found else [],
    })
