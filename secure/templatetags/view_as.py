from django import template

from secure.requestkeys import VIEW_AS_SESSION

register = template.Library()


def _label(spec):
    if spec == "all":
        return "со всеми ключами"
    if spec == "none":
        return "без ключей"
    keys = [s for s in spec.split(",") if s]
    return "с ключами: " + ", ".join(keys) if keys else "без ключей"


@register.inclusion_tag("secure/_view_as.html", takes_context=True)
def view_as_banner(context):
    """Плашка «смотрите как игрок» для сотрудника с включённой подменой ключей."""
    request = context.get("request")
    user = getattr(request, "user", None)
    session = getattr(request, "session", None)
    spec = None
    if session is not None and user is not None and user.is_staff:
        spec = session.get(VIEW_AS_SESSION)
    return {"label": _label(spec) if spec else None}
