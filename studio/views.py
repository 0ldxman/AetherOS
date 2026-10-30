"""Страница студии: оболочка, в которую Vite собрал приложение (studio/frontend -> studio/static/studio/app).

Файлы сборки называются с хешем; какие подключать, говорит манифест Vite. Без сборки страница говорит, как её собрать.
"""
import json
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
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


PREVIEW_APPS = (("mail", "Mail", "✉"), ("wiki", "Wiki", "W"), ("terminal", "Terminal", ">_"), ("map", "Map", "◎"), ("files", "Files", "▤"))


@staff_member_required
def style_preview(request, code):
    """Рабочий стол ОС для предпросмотра стиля в студии: настоящая страница стола с тестовыми приложениями и окнами-образцами.

    Какой стиль и какие токены показывать, говорят параметры preview_os, preview_style и preview_tokens (читает os_style)."""
    import secrets

    from desktop.messages import catalog
    from machines.models import SystemType

    system = get_object_or_404(SystemType, code=code.upper())
    query = request.GET.urlencode()
    suffix = f"?{query}" if query else ""
    apps = [{"id": index, "label": label, "glyph": glyph, "suffix": "", "url": reverse("studio_preview_page", kwargs={"kind": kind}) + suffix}
            for index, (kind, label, glyph) in enumerate(PREVIEW_APPS)]
    return render(request, "desktop/desktop.html", {
        "preview": True, "tunnel": None, "limit": None, "kicks": [], "mail_url": "", "mail_pulse_url": "",
        "machine_name": "preview", "os_name": system.name, "login": "operator",
        "terminal_url": reverse("studio_preview_page", kwargs={"kind": "terminal"}),
        "layout_key": f"studio-preview-{secrets.token_hex(3)}",
        "apps": apps, "files": [], "can_sessions": True, "sessions_url": "#", "logout_url": "#", "lock_url": "#",
        "system_messages": catalog(system.code),
    })


@staff_member_required
def preview_page(request, kind):
    """Страница-образец внутри окна предпросмотра: показывает, как токены стиля ложатся на обычное содержимое."""
    titles = {key: label for key, label, _ in PREVIEW_APPS}
    return render(request, "studio/preview_page.html", {"kind": kind, "title": titles.get(kind, "Page")})
