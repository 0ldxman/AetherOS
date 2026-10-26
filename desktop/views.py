from django.shortcuts import render
from django.urls import reverse

from django.shortcuts import redirect, render
from django.urls import get_script_prefix
from django.views.decorators.csrf import ensure_csrf_cookie

from secure.access import satisfied

from machines.identity import identity_of
from users.aether_auth import GUEST_LOGIN

from .boots import boot_scenes
from .messages import catalog

from machines.current import active_session, current_machine, visible_apps
from machines.models import normalize_suffix

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


@ensure_csrf_cookie  # меню «disconnect» шлёт POST на выход
def desktop(request):
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
            "suffix": normalize_suffix(app.suffix),
            "url": prefix + app.path,
        }
        for app in visible_apps(request, machine)
    ]

    # опрос новых писем нужен только если интерком есть на этом столе
    mail_url = reverse("mail:inbox")
    has_mail = any(item["url"] == mail_url for item in apps)

    return render(request, "desktop/desktop.html", {
        "mail_url": mail_url if has_mail else "",
        "mail_pulse_url": reverse("mail:pulse") if has_mail else "",
        "machine_name": machine.label,
        "login": login,
        "layout_key": layout_key,
        "apps": apps,
        "can_sessions": request.user.is_authenticated,
        "sessions_url": reverse("sessions"),
        "logout_url": reverse("logout"),
        "lock_url": reverse("lock"),
        "system_messages": catalog(machine.system),
    })

def boot(request):
    return render(request, "boot/boot.html", {"boot_config": {"scenes": boot_scenes(identity_of())}})