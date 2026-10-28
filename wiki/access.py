from dataclasses import dataclass

from secure.access import satisfied
from secure.keys import key_slugs


@dataclass(frozen=True)
class State:
    """Итог проверки: видна ли запись и открыта ли она."""
    visible: bool
    open: bool


def guest_keys():
    """Заглушка: у гостя нет ключей.

    Настоящие ключи появятся вместе с машинами и сессиями.
    """
    return frozenset()


# =========================================================
# «Смотреть как игрок» (только для сотрудников)
# =========================================================

VIEW_AS_SESSION = "wiki_view_as"
VIEW_AS_MAX_LEN = 500


def keys_for_mode(mode, listed=()):
    """Набор ключей для режима all / none / custom.

    Берутся только существующие ключи: удалённый или опечатанный slug
    просто не попадёт в набор.
    """
    existing = key_slugs()
    if mode == "all":
        return frozenset(existing)
    if mode == "custom":
        return frozenset(s for s in listed if s in existing)
    return frozenset()


def view_as(request):
    """Подмена ключей сотрудника: "all", "none", "key_a,key_b" или None.

    Включается параметром ?as=..., запоминается в сессии, чтобы можно было
    ходить по ссылкам; ?as=reset выключает. Обычным игрокам не действует.
    """
    user = getattr(request, "user", None)
    session = getattr(request, "session", None)
    if user is None or session is None or not user.is_staff:
        return None
    asked = request.GET.get("as")
    if asked is not None:
        if asked in ("", "reset"):
            session.pop(VIEW_AS_SESSION, None)
        else:
            session[VIEW_AS_SESSION] = asked[:VIEW_AS_MAX_LEN]
    return session.get(VIEW_AS_SESSION)


def held_keys(request):
    """Ключи, которые игрок достал из файлов (kex): слаги файлов его папки /home/.secrets в этой сессии."""
    from filesystem.keystore import slugs_of
    from machines.current import SESSION_KEY
    from machines.models import Session

    if not request.user.is_authenticated or not hasattr(request, "session"):
        return frozenset()
    session_id = request.session.get(SESSION_KEY)
    if not session_id:
        return frozenset()
    return slugs_of(Session.objects.filter(pk=session_id, user=request.user).first())


def request_keys(request):
    """Ключи, под которыми показывается страница: подмена сотрудника или ключи из папки секретов игрока."""
    spec = view_as(request)
    if spec is None:
        return held_keys(request)
    if spec in ("all", "none"):
        return keys_for_mode(spec)
    return keys_for_mode("custom", [s for s in spec.split(",") if s])


def _all_satisfied(conditions, keys):
    # пустое условие satisfied считает открытым, отдельно его обрабатывать не нужно
    return all(satisfied(c, keys) for c in conditions)


def namespace_state(namespace, keys):
    """Состояние неймспейса: условия всей цепочки от корня до него."""
    nodes = namespace.chain()
    return State(
        visible=not any(n.hidden for n in nodes),
        open=_all_satisfied([n.access for n in nodes], keys),
    )


def document_state(doc, keys, via_direct_link=False):
    """Состояние записи: условия неймспейсов цепочки плюс условия самой записи.

    via_direct_link=True обходит только видимость.
    Открытость по ключам остаётся в силе.
    """
    nodes = doc.namespace.chain() if doc.namespace else []
    visible = via_direct_link or not (any(n.hidden for n in nodes) or doc.hidden)
    is_open = _all_satisfied(
        [n.access for n in nodes] + [doc.access], keys
    )
    return State(visible=visible, open=is_open)