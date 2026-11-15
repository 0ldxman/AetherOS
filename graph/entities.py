"""Ноды сущностей: вещь мира по ключу (выбрана в ноде, пришла проводом или найдена по имени) и её свойства сейчас.

Вещь по проводу едет своим ключом: машина — хостом, объект — слагом, персонаж — кодом, раздел — номером, момент — именем,
сервер — адресом, игрок — логином. Нет такой вещи — пустой ключ и пустые свойства.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q


def _blank(kind, out):
    from graph import nodes as N

    sock = N.data_out(kind, out)
    return {"bool": False, "number": 0}.get(sock.type if sock else "", "")


def _key(value):
    return "" if value is None else str(value).strip()


def _machine(key):
    from machines.models import Machine

    return Machine.objects.filter(Q(hostname__iexact=key) | Q(name__iexact=key)).order_by("pk").first() if key else None


def _player(run, key):
    if not key:
        return getattr(run, "user", None)
    return get_user_model().objects.filter(username__iexact=key).first()


def _props(name, key, run):
    """Свойства вещи вида name по ключу: {выход: значение} или None, если вещи нет."""
    if name == "ent:machine":
        from machines.world import power

        m = _machine(key)
        return m and {"value": m.hostname, "name": m.name, "host": m.hostname, "address": m.address, "system": m.system,
                      "up": not power.is_down(m)}
    if name == "ent:server":
        from machines.models import NetResource

        s = NetResource.objects.filter(address__iexact=key).first() if key else None
        return s and {"value": s.address, "address": s.address, "title": s.title}
    if name == "ent:object":
        from filesystem.models import Item

        item = Item.objects.filter(Q(slug=key) | Q(name__iexact=key)).order_by("pk").first() if key else None
        return item and {"value": item.slug, "name": item.name, "format": item.format}
    if name == "ent:character":
        from characters.models import Character

        c = Character.objects.filter(Q(code__iexact=key) | Q(name__iexact=key)).order_by("pk").first() if key else None
        return c and {"value": c.code, "code": c.code, "name": c.name, "callsign": c.signature, "active": c.status == Character.Status.ACTIVE}
    if name == "ent:section":
        from forum.models import Section

        found = Section.objects.filter(pk=int(key)) if key.isdigit() else Section.objects.filter(title__iexact=key)
        s = found.order_by("pk").first() if key else None
        return s and {"value": s.pk, "title": s.title, "archived": s.archived}
    if name == "ent:moment":
        from world import moments
        from world.models import WorldMoment

        m = WorldMoment.objects.filter(Q(name__iexact=key) | Q(title__iexact=key)).order_by("pk").first() if key else None
        return m and {"value": m.name, "title": m.title or m.name, "running": moments.running(m)}
    if name == "ent:player":
        from air.models import Callsign

        user = _player(run, key)
        return user and {"value": user.get_username(), "name": user.get_username(),
                         "callsign": Callsign.objects.filter(user=user).values_list("name", flat=True).first() or ""}
    return None


def read(run, kind, key, out):
    """Значение выхода out ноды сущности kind для ключа key."""
    found = _props(kind.name, _key(key), run)
    return _blank(kind, out) if not found else found.get(out, _blank(kind, out))


def value(run, kind, data, out):
    """«Тег» и «Счётчик»: значение владельца (мир, игрок, вещь; у вещи — общее или для игрока)."""
    from engine import values

    try:
        owner, oid, user = values.target(data, getattr(run, "user", None))
        name = values.check_name(data.get("name"))
    except values.BadValue:
        return _blank(kind, out)
    if kind.name == "ent:tag":
        return values.on(owner, oid, name, user)
    number = values.get(values.COUNT, owner, oid, name, user)
    return values.caption(values.COUNT, owner, oid, name, number) if out == "caption" else number


def _canonical(slug):
    """Объект и его слои по описанию (канонический стек, верхний первым)."""
    from filesystem.layers.compiler import compile_text
    from filesystem.models import Item

    item = Item.objects.filter(slug=slug).first() if slug else None
    if item is None or not (item.state or "").strip():
        return item, []
    try:
        return item, compile_text(item.state)
    except Exception:                               # noqa: BLE001 — испорченное описание: слоёв как будто нет
        return item, []


def layer_key(data):
    """Ключ слоя для графа попытки: «слаг#номер», у «Текущего» — «слаг#*» (любой слой объекта). Нет такого слоя — пусто."""
    slug = _key(data.get("item"))
    mode = data.get("mode") or "current"
    if not slug:
        return ""
    if mode == "current":
        return f"{slug}#*"
    _, canonical = _canonical(slug)
    number = 0
    if mode == "top":
        number = 1
    elif mode == "last":
        number = len(canonical)
    elif mode == "number":
        try:
            number = int(float(str(data.get("number") or 0)))
        except ValueError:
            number = 0
    elif mode == "type":
        number = next((i + 1 for i, layer in enumerate(canonical) if layer.state.name == data.get("kind")), 0)
    return f"{slug}#{number}" if 1 <= number <= len(canonical) else ""


def layer(run, kind, data, out):
    """«Слой объекта»: ключ слоя, его тип и номер, снят ли он у игрока и сколько слоёв у игрока осталось."""
    from filesystem.copies import copies
    from filesystem.layers.stack import load_progress

    key = layer_key(data)
    if not key:
        return _blank(kind, out)
    slug, _, number = key.partition("#")
    item, canonical = _canonical(slug)
    user = _player(run, _key(data.get("player")))
    progress = None
    if user is not None and item is not None:
        live = [c for c in copies(user, slug) if not c.trashed]
        if live:
            try:
                progress = load_progress(live[0].progress, item.state)
            except ValueError:
                progress = None
    removed = progress.removed if progress else 0
    added = progress.added if progress else []
    if number == "*":
        if added:
            position, name = 0, added[0].name
        elif removed < len(canonical):
            position, name = removed + 1, canonical[removed].state.name
        else:
            position, name = 0, ""
    else:
        position = int(number)
        name = canonical[position - 1].state.name
    found = {"value": key, "kind": name, "number": position, "removed": number != "*" and removed >= position,
             "left": len(added) + max(0, len(canonical) - removed)}
    return found.get(out, _blank(kind, out))


def files(run, kind, item, player, machine, out):
    """«Файлы игрока»: есть ли у игрока объект, где лежит, сколько копий, в корзине ли, правил ли он его."""
    from filesystem.copies import copies

    user = _player(run, _key(player))
    item, host = _key(item), _key(machine)
    if user is None or not item:
        return _blank(kind, out)
    where = None
    if host:
        where = _machine(host)
        if where is None:
            return _blank(kind, out)
    found = copies(user, item, where)
    live = [c for c in found if not c.trashed]
    return {"has": bool(live), "where": f"{live[0].host}:{live[0].path}" if live else "", "count": len(live),
            "trash": any(c.trashed for c in found), "edited": any(c.edited for c in live)}.get(out, _blank(kind, out))
