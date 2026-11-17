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


def _taken(machine):
    from machines.access import entry

    return entry.taken(machine)


def _props(name, key, run):
    """Свойства вещи вида name по ключу: {выход: значение} или None, если вещи нет."""
    if name == "ent:machine":
        from machines.world import power

        from graph import sessions
        from machines.world import disks

        m = _machine(key)
        return m and {"value": m.hostname, "name": m.name, "host": m.hostname, "address": m.address, "system": m.system,
                      "up": not power.is_down(m), "disks": disks.of_machine(m), "sessions": sessions.of_machine(m), "display": m.display,
                      "seats": m.seats or 0, "taken": _taken(m)}
    if name == "attr:machine.state":
        from graph import nodes as N

        m = _machine(key)
        found = m and {field: getattr(m, field) for field, *_ in N.STATE}
        return found and {**found, "defects": any(found.values())}
    if name == "attr:machine.time":
        m = _machine(key)
        return m and machine_time(m, getattr(run, "user", None))
    if name == "attr:account.access":
        return access(run, key)
    if name == "ent:os":
        from machines.models import Machine, SystemType

        found = SystemType.objects.filter(Q(code__iexact=key) | Q(name__iexact=key)).order_by("pk").first() if key else None
        return found and {"value": found.code, "code": found.code, "name": found.name, "dialect": found.path_style,
                          "greeting": found.greeting,
                          "machines": list(Machine.objects.filter(system=found.code).exclude(hostname="").order_by("hostname")
                                           .values_list("hostname", flat=True))}
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
    if name == "ent:session":
        from graph import sessions

        return sessions.props(key)
    if name == "ent:volume":
        from machines.world import disks

        v = disks.volume(key)
        return v and {"value": v.slug, "name": v.name or v.slug, "where": disks.where(v)}
    if name == "ent:player":
        from air.models import Callsign

        from graph import sessions
        from machines.models import MachineProfile
        from machines.world import edits

        user = _player(run, key)
        return user and {"value": user.get_username(), "name": user.get_username(),
                         "accounts": [edits.account_key(p) for p in MachineProfile.objects.filter(user=user).exclude(machine__hostname="")
                                      .select_related("machine").order_by("machine__hostname", "login")],
                         "sessions": sessions.find(run, "all", user.get_username()),
                         "callsign": Callsign.objects.filter(profile__machine__hostname="aether-main", profile__user=user).values_list("name", flat=True).first() or ""}
    return None


def machine_time(machine, user=None):
    """«Машина: Время»: пояс, часы машины сейчас (со сдвигом часов игрока), «Включена с» и минуты работы от неё."""
    from datetime import timezone as dt_timezone

    from graph import times
    from machines.world import chrono, clock

    now = clock.now(machine, user)
    booted = machine.booted_at
    return {"zone": str(chrono.zone(machine)), "local": times.text(now.replace(tzinfo=dt_timezone.utc)),
            "booted": times.text(booted.replace(microsecond=0)) if booted else "",
            "uptime": max(0, int((now - booted).total_seconds() // 60)) if booted else 0}


def access(run, key):
    """«Учётка: Доступ»: группы, точки входа, root, блокировка для инициатора, выражение ключей и живые токены."""
    from django.db.models import F
    from django.utils import timezone

    from machines.models import AccountBlock
    from machines.world import edits
    from secure.access import format_condition

    profile = edits.account(key) if key else None
    if profile is None:
        return None
    user = getattr(run, "user", None)
    now = timezone.now()
    blocks = AccountBlock.objects.filter(profile=profile, until__gt=now)
    blocked = blocks.filter(Q(user=None) | Q(user=user)).exists() if user is not None else blocks.filter(user=None).exists()
    tokens = (profile.tokens.filter(Q(max_usage=None) | Q(usage__lt=F("max_usage"))).filter(Q(expires_at=None) | Q(expires_at__gt=now))
              .order_by("pk").values_list("token", flat=True))
    return {"groups": list(profile.groups or []), "endpoints": list(profile.endpoints or []), "root": bool(profile.root), "blocked": blocked,
            "keys": format_condition(profile.key_condition) if profile.key_condition else "", "tokens": list(tokens)}


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


def parse_layer(text, run=None):
    """(игрок, машина, путь, номер слоя) из «игрок@машина:/путь#c2». Чего нет — None."""
    head, _, number = _key(text).rpartition("#")
    found = parse_placement(head, run) if head else None
    return (*found, number) if found is not None and number else None


def _view(user, machine):
    from filesystem import placements

    return placements._view(user, machine)[0]


def layers_of(user, machine, path):
    """Слои файла игрока (все, со снятыми): [LayerInfo]; файла нет — пусто."""
    from filesystem.layers import player

    try:
        return player.of(_view(user, machine), path)
    except (player.LayerError, ValueError):
        return []


def layer(run, kind, data, out):
    """«Слой»: тип, место в стопке, снят ли, сколько попыток осталось, добавлен ли поверх описания, чьё размещение."""
    found = parse_layer(data.get("layer"), run)
    if found is None:
        return _blank(kind, out)
    user, machine, path, number = found
    info = next((i for i in layers_of(user, machine, path) if i.id == number), None)
    if info is None:                                # снятый добавленный слой пропадает
        props = {"removed": True, "added": number.startswith("a"), "placement": placement_key(user, machine.hostname, path)}
    else:
        props = {"type": info.type, "index": info.index, "removed": info.removed, "attempts": -1 if info.attempts_left is None else info.attempts_left,
                 "added": info.added, "placement": placement_key(user, machine.hostname, path)}
    return props.get(out, _blank(kind, out))


def placement_key(user, host, path):
    return f"{user.get_username()}@{host}:{path}" if user is not None and host and path else ""


def parse_placement(text, run=None):
    """(игрок, машина, путь) из «игрок@машина:/путь»; без «игрок@» — инициатор. Чего нет — None."""
    head, _, path = _key(text).partition(":")
    owner, _, host = head.rpartition("@")
    user = _player(run, owner)
    machine = _machine(host)
    if user is None or machine is None or not path:
        return None
    return user, machine, path


def placement(run, kind, data, out):
    """«Размещение»: файл игрока по проводу или по машине и пути — и его свойства сейчас."""
    from filesystem.copies import at

    found = parse_placement(data.get("placement"), run) if _key(data.get("placement")) else None
    if found is None and not _key(data.get("placement")):
        user, machine, path = _player(run, _key(data.get("player"))), _machine(_key(data.get("machine"))), _key(data.get("path"))
        found = (user, machine, path) if user is not None and machine is not None and path else None
    if found is None:
        return _blank(kind, out)
    user, machine, path = found
    copy = at(user, machine, path)
    import posixpath

    props = {"value": placement_key(user, machine.hostname, path), "machine": machine.hostname, "path": path, "name": posixpath.basename(path),
             "exists": copy is not None and not copy.trashed, "trash": copy is not None and copy.trashed, "edited": bool(copy and copy.edited),
             "item": copy.item if copy else ""}
    if out == "layers":                             # все слои файла, верхний первым (со снятыми)
        key = props["value"]
        return [f"{key}#{info.id}" for info in layers_of(user, machine, path)]
    return props.get(out, _blank(kind, out))


def find(run, kind, data):
    """«Размещение: Найти»: список «игрок@машина:/путь» по объекту (пусто — любые файлы), машине, пути и корзине."""
    from filesystem.copies import find as search

    user = _player(run, _key(data.get("player")))
    if user is None:
        return []
    machine = None
    if _key(data.get("machine")):
        machine = _machine(_key(data.get("machine")))
        if machine is None:
            return []
    return [placement_key(user, copy.host, copy.path)
            for copy in search(user, _key(data.get("item")) or None, machine, _key(data.get("path")), data.get("where") or "live")]




def mount(run, kind, data, out):
    """«Машина: Диск»: по проводу «хост:/точка» или по машине и точке — что там стоит сейчас."""
    from machines.world import disks

    key = _key(data.get("mount"))
    if not key:
        machine = _machine(_key(data.get("machine")))
        key = disks.key_of(machine, _key(data.get("point")))
    found = disks.props(key)
    return (found or {}).get(out, _blank(kind, out))


def account(run, kind, data, out):
    """«Учётка»: по проводу «логин@хост» или по машине и логину — её свойства сейчас (доступ — в «Учётка: Доступ»)."""
    from machines.models import MachineProfile
    from machines.world import edits

    key = _key(data.get("account"))
    if key:
        profile = edits.account(key)
    else:
        machine, login = _machine(_key(data.get("machine"))), _key(data.get("login"))
        profile = MachineProfile.objects.filter(machine=machine, login=login).first() if machine is not None and login else None
    if profile is None:
        return _blank(kind, out)
    from graph import sessions

    props = {"value": edits.account_key(profile), "machine": profile.machine.hostname or "", "login": profile.login, "name": profile.name,
             "sessions": sessions.of_account(profile), "mail": profile.mail}
    return props.get(out, _blank(kind, out))
