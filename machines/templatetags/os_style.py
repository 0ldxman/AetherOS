"""Стиль ОС машины игрока в шаблонах: {% os_style_slug %} для <html>, {% os_theme %} после токенов и {% os_tokens %} в конце <head>.

ОС берётся у машины, на рабочем столе которой игрок сейчас; без сессии (вход, загрузка) у входного узла. Сотрудник студии может
посмотреть чужой стиль: ?preview_os=КОД. Подключается только базовым шаблоном ui/base.html, поэтому админка и студия стиль не получают."""
import json
from urllib.parse import urlencode

from django import template
from django.db.models import Subquery
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from machines.current import MAIN_HOSTNAME, current_machine
from machines.models import Machine, SystemType
from machines.world import styles, wallpaper

register = template.Library()


def _state(request):
    """(слаг стиля, токены) для запроса; считается один раз."""
    found = getattr(request, "_os_style", None)
    if found is not None:
        return found
    system = None
    user = getattr(request, "user", None)
    code = request.GET.get("preview_os") if user is not None and user.is_authenticated and user.is_staff else None
    if code:
        system = SystemType.objects.filter(code=code.upper()).first()
    if system is None:
        machine = None
        if user is not None and hasattr(request, "session"):          # запрос без сессии (тесты, служебные страницы): как у входного узла
            try:
                machine = current_machine(request)
            except Machine.DoesNotExist:
                machine = None
        if machine is not None:
            system = machine.system_type
        else:                                                           # один запрос: ОС входного узла
            system = SystemType.objects.filter(code=Subquery(Machine.objects.filter(hostname=MAIN_HOSTNAME).values("system")[:1])).first()
    found = (system.style, system.style_tokens, system.code, system.wallpaper) if system is not None and system.style in styles.STYLES else (styles.DEFAULT_STYLE, {}, "", {})
    request._os_widgets = (system.widgets or {}) if system is not None else {}
    request._os_places = (system.widget_places or {}) if system is not None else {}
    request._os_parts = (system.style_parts or {}) if system is not None else {}
    if user is not None and user.is_authenticated and user.is_staff:          # предпросмотр несохранённого стиля в студии
        found = _preview(request, found) or found
        if request.GET.get("preview_widgets"):
            try:
                request._os_widgets = json.loads(request.GET["preview_widgets"])
            except ValueError:
                pass
        if request.GET.get("preview_parts"):
            try:
                request._os_parts = json.loads(request.GET["preview_parts"])
            except ValueError:
                pass
        if request.GET.get("preview_places"):
            try:
                request._os_places = json.loads(request.GET["preview_places"])
            except ValueError:
                pass
    request._os_style = found
    return found


def _panel(request):
    """Раскладка панели ОС этого запроса (её часть style_parts)."""
    from machines.world import styles

    return styles.clean_parts(getattr(request, "_os_parts", {})).get("panel")


def _look(request):
    from machines.world import panel

    return panel.of(_state(request)[0], _panel(request))["look"]


def widget_state(request):
    """{элемент стола: включён} для ОС этого запроса (machines/world/widgets.py); родное считается по виду панели."""
    from machines.world import widgets

    return widgets.resolve(_look(request), getattr(request, "_os_widgets", {}))


def _preview(request, found):
    """(слаг, токены, код, картинка) из preview_style, preview_tokens и preview_wall запроса сотрудника или None; невалидное отбрасывается."""
    slug = request.GET.get("preview_style")
    if slug not in styles.STYLES:
        return None
    try:
        tokens = json.loads(request.GET.get("preview_tokens") or "{}")
    except ValueError:
        tokens = {}
    if not isinstance(tokens, dict) or styles.problems(slug, tokens):
        tokens = {}
    picture = found[3]
    if request.GET.get("preview_wall"):
        try:
            picture = json.loads(request.GET["preview_wall"])
        except ValueError:
            picture = {}
        if wallpaper.problems(picture):
            picture = found[3]
    return slug, tokens, found[2], picture


@register.simple_tag(takes_context=True)
def os_widgets_css(context):
    """<style>, прячущий выключенные у ОС родные элементы стола (пусто, если всё включено)."""
    from machines.world import widgets

    request = context.get("request")
    if request is None:
        return ""
    block = widgets.hidden_css(_look(request), getattr(request, "_os_widgets", {}))
    return mark_safe(f'<style id="os-widgets">{block}</style>') if block else ""


@register.simple_tag(takes_context=True)
def os_panel(context):
    """Главная панель: шаблон вида (desktop/panels/<вид>.html) с элементами в слотах (machines/world/panel.py)."""
    from django.template.loader import render_to_string

    from machines.world import panel

    request = context.get("request")
    slug = _state(request)[0] if request is not None else styles.DEFAULT_STYLE
    data = _panel(request) if request is not None else None
    look = panel.of(slug, data)["look"]
    flat = context.flatten()
    flat["panel"] = panel.elements(slug, data)
    return mark_safe(render_to_string(f"desktop/panels/{look}.html", flat, request=request))


@register.simple_tag(takes_context=True)
def os_slot(context, slot):
    """Что стол добавляет к виду панели (slot "desk"): свой док и всплывающие меню запуска и журнал, если у вида их нет."""
    from django.template.loader import render_to_string

    from machines.world import panel, widgets

    request = context.get("request")
    if request is None or slot != "desk":
        return ""
    slug = _state(request)[0]
    data = _panel(request)
    found = panel.of(slug, data)
    look, placed = found["look"], panel.placed(slug, data)
    edge = found["edge"]
    side = {"start": "left", "center": "center", "end": "right"}
    desk = {
        "edge": edge,
        "dock": widgets.dock_place(look, getattr(request, "_os_widgets", {}), getattr(request, "_os_places", {})),
        "launcher_panel": bool({"launcher", "search"} & set(placed)) and look not in panel.NATIVE_LAUNCHER_PANEL,
        "notices_panel": "notices" in placed and look not in panel.NATIVE_NOTICES_PANEL,
        "search_in_panel": "search" not in placed,
        "launcher_side": side[placed.get("launcher", placed.get("search", "start"))],
        "notices_side": side[placed.get("notices", "end")],
    }
    if not (desk["dock"] or desk["launcher_panel"] or desk["notices_panel"]):
        return ""
    return mark_safe(render_to_string("desktop/elements/desk.html", {**context.flatten(), **desk}))


@register.simple_tag(takes_context=True)
def os_widget(context, key):
    """Включён ли элемент оболочки у ОС: "1" или "0" (для data-атрибутов)."""
    request = context.get("request")
    return "1" if request is None or widget_state(request).get(key, True) else "0"


@register.simple_tag(takes_context=True)
def os_style_slug(context):
    request = context.get("request")
    return _state(request)[0] if request is not None else styles.DEFAULT_STYLE


@register.simple_tag(takes_context=True)
def app_icon(context, name):
    """Адрес картинки иконки приложения в стиле ОС машины игрока (пусто: рисуется текстовый значок)."""
    from desktop.icons import icon_url

    request = context.get("request")
    slug = _state(request)[0] if request is not None else styles.DEFAULT_STYLE
    return icon_url(slug, name)


@register.simple_tag(takes_context=True)
def os_theme(context):
    request = context.get("request")
    slug = _state(request)[0] if request is not None else styles.DEFAULT_STYLE
    links = [f"ui/themes/{slug}.css"] if styles.STYLES[slug].css else []
    links.append("ui/parts/windows.css")       # окна раньше частей: окна сообщений перекрашивает часть notice
    chosen = styles.parts(slug, getattr(request, "_os_parts", {}) if request is not None else {})
    links += [path for path in (styles.part_file(part, chosen[part]) for part in styles.PARTS) if path]
    return mark_safe("".join(format_html('<link rel="stylesheet" href="{}">', static(path)) for path in links))


@register.simple_tag(takes_context=True)
def os_parts(context):
    """Атрибуты частей стиля для <html>: data-win-title, data-win-frame…, data-notice, data-panel, data-dock (с ведущим пробелом)."""
    request = context.get("request")
    slug = _state(request)[0] if request is not None else styles.DEFAULT_STYLE
    custom = getattr(request, "_os_parts", {}) if request is not None else {}
    return mark_safe("".join(format_html(' data-{}="{}"', part, kind) for part, kind in styles.parts(slug, custom).items()))


@register.simple_tag(takes_context=True)
def os_tokens(context):
    request = context.get("request")
    block = styles.css(_state(request)[1]) if request is not None else ""
    return mark_safe(f'<style id="os-style">{block}</style>') if block else ""


@register.simple_tag(takes_context=True)
def os_wallpaper(context):
    """Картинка и узор рабочего стола ОС (в начале <body> оболочки); пусто, если автор их не задал."""
    request = context.get("request")
    if request is None:
        return ""
    slug, tokens, code, picture = _state(request)
    if not code:
        return ""
    data = wallpaper.clean(picture)
    from django.urls import reverse

    query = {"v": data["file_id"]}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:          # сотрудник видит и ещё не сохранённый файл (предпросмотр в студии)
        query["file"] = data["file_id"]
    url = reverse("os_wallpaper", kwargs={"code": code}) + "?" + urlencode(query)
    return wallpaper.render(url, data, wallpaper.style_look(slug, tokens))
