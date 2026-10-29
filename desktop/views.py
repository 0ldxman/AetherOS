from django.shortcuts import render
from django.urls import reverse

from django.shortcuts import redirect, render
from django.urls import get_script_prefix
from django.views.decorators.csrf import ensure_csrf_cookie

from secure.access import satisfied

from machines.world.identity import identity_of
from users.aether_auth import GUEST_LOGIN

from desktop.boots import boot_scenes
from desktop.messages import catalog

from machines.current import active_session, current_machine, desktop_entries, is_app, visible_apps

# Create your views here.

APPS = [
    {
        "id": "wiki",
        "label": "aether",
        "glyph": "W",
        "suffix": ".db",
        "url_name": "wiki:home",
    },
    {
        "id": "mail",
        "label": "intercom",
        "glyph": "@",
        "suffix": ".conn",
        "url_name": "sessions",
    },
    {
        "id": "terminal",
        "label": "console",
        "glyph": ">_",
        "suffix": ".sh",
        "url_name": "sessions",
    },
    {
        "id": "sessions",
        "label": "sessions",
        "glyph": "S",
        "suffix": ".mon",
        "url_name": "sessions",
    },
    {
        "id": "map",
        "label": "world",
        "glyph": "M",
        "suffix": ".map",
        "url_name": "map:index",
    },
]



def _identity(request, machine):
    """Кто подключён и куда: (логин на машине, ключ раскладки стола).

    Раскладка (иконки, окна) запоминается в браузере отдельно для каждой
    пары «игрок и машина»: у разных машин свой стол.
    """
    if request.user.is_authenticated:
        login = active_session(request).profile.login
        owner = f"u{request.user.pk}"
    else:
        login = GUEST_LOGIN
        owner = "guest"   # ключ раскладки не зависит от имени, чтобы сохранённые столы не пропали
    return login, f"{owner}-m{machine.pk}"


def _file_icons(request, machine):
    """Обычные файлы стола: значок открывает окно файла по его виду. Закрытый слоями файл виден, но не открывается, пока слои не сняты."""
    from filesystem.content.window import resolve_content

    icons = []
    for entry in desktop_entries(request, machine):
        if is_app(entry):
            continue
        content = resolve_content(entry, entry.path, entry.name)
        icons.append({"id": f"file:{entry.path}", "label": entry.name, "glyph": "▤", "url": content.url or "", "closed": not content.url})
    return icons


@ensure_csrf_cookie  # меню «disconnect» шлёт POST на выход
def desktop(request):
    from machines.network import bridge
    from terminal.views import _clock, _kicks

    kicks = _kicks(request) if request.user.is_authenticated else []
    machine = current_machine(request)

    if machine is None:
        return redirect("boot")

    login, layout_key = _identity(request, machine)

    prefix = get_script_prefix().rstrip("/")

    apps = [
        {
            "id": app.pk,
            "label": app.label,
            "glyph": app.glyph,
            "suffix": app.suffix,
            "url": prefix + app.path,
        }
        for app in visible_apps(request, machine)
    ]

    files = _file_icons(request, machine)

    # опрос новых писем нужен только если интерком есть на этом столе
    mail_url = reverse("mail:inbox")
    has_mail = any(item["url"] == mail_url for item in apps)

    # мост: игрок на чужой машине, и терминал-«дыра» открыт на столе сразу
    from machines.network import bridge

    tunnel = None
    limit = None
    if request.user.is_authenticated:
        node = next((row for row in bridge.tabs(request) if row["desktop"]), None)
        limit = {"deadline": node["deadline"], "now": _clock(), "tick_url": reverse("terminal:tick")} if node and node["deadline"] else None
    if request.user.is_authenticated and bridge.depth(request) > 0:
        tunnel = {
            "label": f"rcon: {login}@{machine.label}",
            "url": reverse("terminal:index"),      # reverse уже содержит префикс сайта
            "close_url": reverse("terminal:bridge_close"),
        }

    return render(request, "desktop/desktop.html", {
        "tunnel": tunnel,
        "limit": limit,
        "kicks": kicks,
        "mail_url": mail_url if has_mail else "",
        "mail_pulse_url": reverse("mail:pulse") if has_mail else "",
        "machine_name": machine.label,
        "login": login,
        "layout_key": layout_key,
        "apps": apps,
        "files": files,
        "can_sessions": request.user.is_authenticated,
        "sessions_url": reverse("sessions"),
        "logout_url": reverse("logout"),
        "lock_url": reverse("lock"),
        "system_messages": catalog(machine.system),
    })

def boot(request):
    return render(request, "boot/boot.html", {"boot_config": {"scenes": boot_scenes(identity_of())}})