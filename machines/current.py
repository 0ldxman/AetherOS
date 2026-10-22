from decimal import Decimal
from machines.models import Machine, MachineProfile, Session
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve

from secure.access import satisfied
from wiki.access import player_keys

NULL_HOSTNAME = "aether-null"
MAIN_HOSTNAME = "aether-main"
SESSION_KEY = "machine_session_id"
AUTO_PROFILE_FREQ = Decimal("0.000")


def active_session(request):
    if not request.user.is_authenticated:
        return None

    session_id = request.session.get(SESSION_KEY)

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
        return Machine.objects.get(hostname=NULL_HOSTNAME)

    return None

def visible_apps(request, machine):
    keys = player_keys(request.user)

    return [
        app
        for app in machine.machine_apps.all()
        if app.key_condition is None or satisfied(app.key_condition, keys)
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
