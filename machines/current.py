from decimal import Decimal
from types import SimpleNamespace
from machines.models import Machine, MachineProfile, Session
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve

from secure.access import satisfied
from secure.requestkeys import request_keys

NULL_HOSTNAME = "aether-null"
MAIN_HOSTNAME = "aether-main"
SESSION_KEY = "machine_session_id"
AUTO_PROFILE_FREQ = Decimal("0.000")


def active_session(request):
    """Сессия рабочего стола игрока: её учётку читают стол, файлы, почта, ключи. Рабочее место одно на игрока, во всех
    браузерах одно и то же (machines.models.Workplace)."""
    if not request.user.is_authenticated:
        return None

    # за запрос эту функцию зовут и middleware, и вид, и шаблон: держим найденную сессию, пока выбор не сменился
    memo = getattr(request, "_active_session", None)
    if memo is not None and memo[0] == request.user.pk and not _wants_sign_in(request):
        return memo[1]

    session = _active_session(request)
    request._active_session = (request.user.pk, session)
    return session


def _wants_sign_in(request):
    session = getattr(request, "session", None)
    return bool(session is not None and session.get(SESSION_KEY))


def _active_session(request):
    if _wants_sign_in(request):                     # «сесть за эту учётку»: вход с экрана замка, подготовка снимков, тесты
        sign_in(request.user, Session.objects.filter(pk=request.session.pop(SESSION_KEY), user=request.user).first())
        request.__dict__.pop("_workplace", None)
    return workplace_for(request).desktop


def workplace_for(request):
    """Рабочее место игрока запроса: за запрос читается один раз (мосты сбрасывают его, когда меняют стол или терминал)."""
    place = request.__dict__.get("_workplace")
    if place is None or place.user_id != request.user.pk:
        place = request.__dict__["_workplace"] = workplace_of(request.user)
    return place


def current_session(request):
    """Сессия рабочего стола, если игрок уже в игре (рабочее место есть), иначе None — без создания учётки и места."""
    from machines.models import Workplace

    if not getattr(request.user, "is_authenticated", False):
        return None
    if _wants_sign_in(request) or request.__dict__.get("_workplace") is not None:
        return active_session(request)
    place = Workplace.objects.select_related("desktop__profile__machine").filter(user=request.user).first()
    return place.desktop if place is not None else None


def workplace_of(user):
    """Рабочее место игрока; нет его или указатели потерялись — стол и терминал на корне (своя учётка на aether-main)."""
    from machines.models import Workplace

    related = ("desktop__profile__machine", "terminal__profile__machine")
    place = Workplace.objects.select_related(*related).filter(user=user).first()
    if place is not None and place.desktop_id and place.terminal_id:
        return place
    root = Session.objects.filter(user=user, parent__isnull=True).order_by("pk").first()
    if root is None:
        root = Session.objects.create(user=user, profile=home_account(user), via=Session.Via.LOCAL, desk=True)
    Workplace.objects.update_or_create(user=user, defaults={"desktop": root, "terminal": root})
    return Workplace.objects.select_related(*related).get(user=user)


def sign_in(user, session):
    """Сесть за учётку сессии session: она становится корнем, остальные подключения игрока закрываются."""
    from machines.models import Workplace

    if session is None:
        return
    others = list(Session.objects.filter(user=user).exclude(pk=session.pk).select_related("profile__machine"))
    Session.objects.filter(pk__in=[row.pk for row in others]).delete()
    if others:
        from machines.network.bridge import announce_left

        announce_left(user, others)
    Session.objects.filter(pk=session.pk).update(parent=None, via=Session.Via.LOCAL, desk=True, deadline=None)
    Workplace.objects.update_or_create(user=user, defaults={"desktop": session, "terminal": session})


def home_account(user):
    """Своя учётка игрока на aether-main (его загончик, почта, ключи): заводится при первом входе в игру. Снаружи на неё не
    зайти (точек входа нет); корень его подключений."""
    machine = Machine.objects.get(hostname=MAIN_HOSTNAME)
    profile = MachineProfile.objects.filter(machine=machine, user=user).first()
    if profile is None:
        profile = MachineProfile.objects.create(machine=machine, user=user, name=user.get_username(), login=user.get_username(),
                                                freq=AUTO_PROFILE_FREQ)
    return profile


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
    """Файлы рабочего стола записи (без папок и скрытого): приложения и обычные файлы. За запрос читаются один раз.

    Приложения по умолчанию для всех учёток лежат в шаблонной папке тома (/home/{login}/Desktop): вид машины сам
    подставляет логин учётки (filesystem.machine_view.build)."""
    from filesystem.machine_view import view_for
    from machines.world import places
    from users.aether_auth import GUEST_LOGIN

    cache = request.__dict__.setdefault("_desktop_entries", {})
    if machine.pk not in cache:
        signed = request.user.is_authenticated
        login = active_session(request).profile.login if signed else GUEST_LOGIN
        desktop = places.resolve(machine, "desktop", login)
        view = view_for(machine, request.user if signed else None, login=login)
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
            pk=entry.item.pk, label=spec.label, icon=spec.icon, suffix=spec.suffix, path=spec.path, order=spec.order,
            conditions=entry.conditions, name=entry.name, volumes=spec.volumes,
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
