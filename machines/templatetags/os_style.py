"""Стиль ОС машины игрока в шаблонах: {% os_style_slug %} для <html>, {% os_theme %} после токенов и {% os_tokens %} в конце <head>.

ОС берётся у машины, на рабочем столе которой игрок сейчас; без сессии (вход, загрузка) у входного узла. Сотрудник студии может
посмотреть чужой стиль: ?preview_os=КОД. Подключается только базовым шаблоном ui/base.html, поэтому админка и студия стиль не получают."""
from django import template
from django.db.models import Subquery
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from machines.current import MAIN_HOSTNAME, current_machine
from machines.models import Machine, SystemType
from machines.world import styles

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
    found = request._os_style = (system.style, system.style_tokens) if system is not None and system.style in styles.STYLES else (styles.DEFAULT_STYLE, {})
    return found


@register.simple_tag(takes_context=True)
def os_style_slug(context):
    request = context.get("request")
    return _state(request)[0] if request is not None else styles.DEFAULT_STYLE


@register.simple_tag(takes_context=True)
def os_theme(context):
    request = context.get("request")
    slug = _state(request)[0] if request is not None else styles.DEFAULT_STYLE
    if not styles.STYLES[slug].css:
        return ""
    return format_html('<link rel="stylesheet" href="{}">', static(f"ui/themes/{slug}.css"))


@register.simple_tag(takes_context=True)
def os_tokens(context):
    request = context.get("request")
    block = styles.css(_state(request)[1]) if request is not None else ""
    return mark_safe(f'<style id="os-style">{block}</style>') if block else ""
