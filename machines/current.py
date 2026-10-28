from decimal import Decimal
from types import SimpleNamespace
from machines.models import Machine, MachineProfile, Session
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve

from secure.access import satisfied
from wiki.access import request_keys

NULL_HOSTNAME = "aether-null"
MAIN_HOSTNAME = "aether-main"
SESSION_KEY = "machine_session_id"
AUTO_PROFILE_FREQ = Decimal("0.000")


def active_session(request):
    if not request.user.is_authenticated:
        return None

    session_id = request.session.get(SESSION_KEY)

    # за запрос эту функцию зовут и middleware, и вид, и шаблон: держим найденную сессию, пока выбор не сменился
    memo = getattr(request, "_active_session", None)
    if memo is not None and memo[0] == (session_id, request.user.pk):
        return memo[1]

    session = _active_session(request, session_id)
    request._active_session = ((request.session.get(SESSION_KEY), request.user.pk), session)
    return session


def _active_session(request, session_id):
    if session_id:
        session = (
            Session.objects
            .select_related("profile__machine")
            .filter(pk=session_id, user=request.user)
            .first()
        )

        if session is not None:
            return session

    machine = Machine.objects.get(hostname=MAIN_HOSTNAME)

    profile = MachineProfile.objects.filter(
        machine=machine,
        user=request.user,
    ).first()

    if profile is None:
        profile = MachineProfile.objects.create(
            machine=machine,
            user=request.user,
            name=request.user.get_username(),
            login=request.user.get_username(),
            freq=AUTO_PROFILE_FREQ,
        )

    session = Session.objects.create(
        user=request.user,
        profile=profile,
    )
    request.session[SESSION_KEY] = session.pk

    return session

def current_machine(request):
    if request.user.is_authenticated:
        return active_session(request).profile.machine

    if request.session.get("guest"):
        machine = getattr(request, "_null_machine", None)
        if machine is None:
            machine = request._null_machine = Machine.objects.get(hostname=NULL_HOSTNAME)
        return machine

    return None

def _machine_apps(request, machine):
    """Иконки машины: приложения на рабочем столе записи, за запрос читаются один раз."""
    cache = request.__dict__.setdefault("_machine_apps", {})
    if machine.pk not in cache:
        cache[machine.pk] = _desktop_apps(request, machine)
    return cache[machine.pk]


def desktop_entries(request, machine):
    """Файлы рабочего стола записи (без папок и скрытого): приложения и обычные файлы. За запрос читаются один раз."""
    from filesystem.machine_view import MachineView
    from machines import places
    from users.aether_auth import GUEST_LOGIN

    cache = request.__dict__.setdefault("_desktop_entries", {})
    if machine.pk not in cache:
        signed = request.user.is_authenticated
        login = active_session(request).profile.login if signed else GUEST_LOGIN
        desktop = places.resolve(machine, "desktop", login)
        view = MachineView(machine, request.user if signed else None)
        cache[machine.pk] = [] if desktop is None else [
            entry for entry in view.children(desktop) if not entry.is_dir and not entry.hidden
        ]
    return cache[machine.pk]


def is_app(entry):
    from filesystem import appfile

    return entry.item is not None and entry.item.format == appfile.APP_FORMAT


def _desktop_apps(request, machine):
    from django.core.exceptions import ValidationError

    from filesystem import appfile

    found = []
    for entry in desktop_entries(request, machine):
        if not is_app(entry):
            continue
        try:
            spec = appfile.parse(entry.item.body)
        except ValidationError:
            continue
        found.append(SimpleNamespace(
            pk=entry.item.pk, label=spec.label, glyph=spec.glyph, suffix=spec.suffix, path=spec.path, order=spec.order,
            conditions=entry.conditions, name=entry.name,
        ))
    return sorted(found, key=lambda app: (app.order, app.name.casefold()))


def visible_apps(request, machine):
    keys = request_keys(request)

    return [
        app
        for app in _machine_apps(request, machine)
        if all(satisfied(condition, keys) for condition in app.conditions)
    ]


def icon_matches(request):
    machine = current_machine(request)

    if machine is None:
        return []

    matches = []

    for app in visible_apps(request, machine):
        try:
            matches.append(resolve(urlsplit(app.path).path))
        except Resolver404:
            continue

    return matches


def machine_has_app(request, namespace):
    return any(
        namespace in match.namespaces
        for match in icon_matches(request)
    )

def wiki_allows(request, match):
    for icon in icon_matches(request):
        if "wiki" not in icon.namespaces:
            continue

        if icon.url_name != "direct":
            return True

        if match.url_name == "direct" and icon.kwargs == match.kwargs:
            return True

    return False
