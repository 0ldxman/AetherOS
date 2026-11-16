from django.shortcuts import render
from django.urls import reverse

from django.shortcuts import redirect, render
from django.urls import get_script_prefix
from django.views.decorators.csrf import ensure_csrf_cookie

from secure.access import satisfied

from machines.models import Machine
from machines.world.identity import identity_of
from users.aether_auth import GUEST_LOGIN

from scenes.boots import boot_scenes
from desktop.icons import glyph
from desktop.messages import catalog

from machines.current import active_session, current_machine, desktop_entries, is_app, visible_apps

# Create your views here.

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
        icons.append({"id": f"file:{entry.path}", "label": entry.name, "icon": "file", "ascii": glyph("file"), "url": content.url or "", "closed": not content.url})
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
            "icon": app.icon,
            "ascii": glyph(app.icon),
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

    # новости и поддержка: бейдж и уведомление, если их приложение есть на этом столе
    feeds = []
    for name in ("news", "support"):
        url = reverse(f"{name}:index")
        if any(item["url"] == url for item in apps):
            feeds.append({"url": url, "pulse": reverse(f"{name}:pulse"), "toast": f"{name}_new"})

    from machines.world import chrono

    return render(request, "desktop/desktop.html", {
        "game_clock": chrono.client(machine, request.user if request.user.is_authenticated else None),
        "feeds": feeds,
        "tunnel": tunnel,
        "limit": limit,
        "kicks": kicks,
        "mail_url": mail_url if has_mail else "",
        "mail_pulse_url": reverse("mail:pulse") if has_mail else "",
        "machine_name": machine.label,
        "screen_noise": machine.screen_noise,
        "terminal_url": reverse("terminal:index"),
        "os_name": machine.system_type.name if machine.system_type else machine.system,
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
    ident = identity_of()
    system = Machine.objects.filter(hostname=ident.hostname).values_list("system", flat=True).first() or "AETHER"
    return render(request, "boot/boot.html", {"boot_config": {"scenes": boot_scenes(ident, system)}})

class _WallpaperFile:
    """Файл картинки рабочего стола для отдачи из Nextcloud: кэша метаданных у него нет."""

    def __init__(self, file_id):
        self.file_id = file_id

    def apply_file(self, file):
        return False


def wallpaper(request, code):
    """Картинка рабочего стола ОС (SystemType.wallpaper). Ключи не проверяются: файл выбрал автор для этой ОС.
    Сотрудник студии может посмотреть ещё не сохранённый файл: ?file=id (предпросмотр стиля)."""
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    from assets.views import _serve_asset_file
    from machines.models import SystemType
    from machines.world import wallpaper as picture

    system = get_object_or_404(SystemType, code=code.upper())
    data = picture.clean(system.wallpaper)
    file_id = data["file_id"]
    if request.user.is_staff and request.GET.get("file"):
        file_id = request.GET["file"]
    if not file_id or picture.problems({**data, "file_id": file_id}):
        raise Http404
    response = _serve_asset_file(request, _WallpaperFile(file_id))
    response["Cache-Control"] = "public, max-age=3600"
    return response


def cards_events(request):
    """Карточка «События» на столе: ближайшие моменты мира, как в команде at (идущие и предстоящие, видимые игроку)."""
    from django.http import JsonResponse

    from machines.world import chrono
    from secure.requestkeys import request_keys
    from world import moments as world_moments

    machine = current_machine(request)
    profile = active_session(request).profile if request.user.is_authenticated and machine is not None else None
    game = chrono.game_now()
    rows = world_moments.board(machine, profile, request_keys(request), where="in_list")[:5]
    return JsonResponse({"rate": chrono.rate_now(), "rows": [
        {"title": row["title"], "state": row["state"],
         "left": int(((row["end"] if row["state"] == "live" else row["start"]) - game).total_seconds())}
        for row in rows
    ]})


def moments(request):
    """Полоса моментов мира на столе: идущие и скорые (за «предупреждать за» минут) видимые этому игроку на этой машине."""
    from django.http import JsonResponse

    from machines.world import chrono
    from secure.requestkeys import request_keys
    from world import moments as world_moments

    machine = current_machine(request)
    profile = active_session(request).profile if request.user.is_authenticated and machine is not None else None
    game = chrono.game_now()
    rows = [row for row in world_moments.board(machine, profile, request_keys(request), where=None)
            if row["state"] in ("live", "soon") and (row["ticker"] or row["toast"])]
    return JsonResponse({"rate": chrono.rate_now(), "rows": [
        {"name": row["name"], "title": row["title"], "state": row["state"], "ticker": row["ticker"], "toast": row["toast"],
         "start": int(row["start"].timestamp()),
         "left": int(((row["end"] if row["state"] == "live" else row["start"]) - game).total_seconds())}
        for row in rows
    ]})


def _where(request):
    """(игрок, учётка) текущей сессии или (None, None)."""
    try:
        session = active_session(request) if request.user.is_authenticated and not request.user.is_staff else None
    except Machine.DoesNotExist:                    # мир без главной машины: игроку некуда войти
        session = None
    if session is None or session.profile is None:
        return None, None
    return request.user, session.profile


def push(request):
    """Эффекты сценариев для этого игрока (engine/push.py): окна, уведомления, бегущая строка, чёрный экран, текст и сцены;
    offers — окна с выбором, открытые ему сценариями (висят, пока он не ответит)."""
    from django.http import JsonResponse

    from engine import push as queue
    from graph import offers

    user, profile = _where(request)
    found = offers.choices(user, profile.machine.hostname, profile.login) if profile is not None else []
    items = []
    if request.user.is_authenticated and not request.user.is_staff:
        from machines.models import Workplace

        place = Workplace.objects.select_related("desktop__profile", "terminal__profile").filter(user=request.user).first()   # не заводит
        items = queue.take(request.user, desk=place.desktop.profile if place and place.desktop_id else None,
                           terminal=place.terminal.profile if place and place.terminal_id else None)
    kicks = []
    if request.user.is_authenticated and not request.user.is_staff:
        from machines.network import bridge

        bridge.expire(request)                         # обрыв по помехам или сценарием: стол узнаёт при опросе
        waiting = request.session.get(bridge.KICKS_KEY, [])
        kicks = [kick for kick in waiting if kick.get("desktop")]
        if kicks:                                      # обрывы терминала остаются ему
            request.session[bridge.KICKS_KEY] = [kick for kick in waiting if not kick.get("desktop")]
    return JsonResponse({"items": items, "kicks": kicks,
                         "offers": [{"id": view.key, "title": view.spec.get("title") or "", "text": view.spec.get("message") or "",
                                     "buttons": view.spec["buttons"]} for view in found]})


def choose(request):
    """Кнопка окна с выбором: {"offer", "button"}."""
    import json

    from django.http import JsonResponse

    from graph import offers

    user, profile = _where(request)
    if request.method != "POST" or profile is None:
        return JsonResponse({"error": "no session"}, status=403)
    data = json.loads(request.body or b"{}")
    done = offers.choose(user, profile.machine.hostname, profile.login, str(data.get("offer") or ""), str(data.get("button") or ""), profile.machine)
    return JsonResponse({"ok": done}, status=200 if done else 404)


def file_actions(request):
    """Действия над файлом окна: GET ?path= — кнопки, POST {"offer", "path"} — нажать."""
    import json

    from django.http import JsonResponse

    from filesystem.machine_view import view_for
    from graph import offers

    user, profile = _where(request)
    if profile is None:
        return JsonResponse({"actions": []})
    data = json.loads(request.body or b"{}") if request.method == "POST" else request.GET
    path = str(data.get("path") or "").rstrip("/")
    entry = view_for(profile.machine, user, login=profile.login).get(path) if path.startswith("/") else None
    if entry is None or entry.is_dir:
        return JsonResponse({"actions": []}, status=404 if request.method == "POST" else 200)
    slug = getattr(entry.item, "slug", "") or ""
    host, login = profile.machine.hostname, profile.login
    if request.method == "POST":
        done = offers.act_on_file(user, host, login, str(data.get("offer") or ""), path, slug, profile.machine)
        return JsonResponse({"ok": done}, status=200 if done else 404)
    found = offers.file_actions(user, host, login, path, slug)
    caption = next((view.spec["caption"] for view in found if view.spec.get("caption")), "")
    return JsonResponse({"actions": [{"id": view.key, "title": view.spec.get("title") or "…"} for view in found], "caption": caption})
