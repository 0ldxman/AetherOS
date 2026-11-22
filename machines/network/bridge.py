"""Мост: игрок входит с одной машины на другую из терминала (rcon, rshell).

Состояние живёт в базе, одно на игрока (во всех его браузерах то же самое). Это дерево подключений:

    узел        одно подключение — строка Session (игрок, учётка, родитель, как вошли, папка терминала, срок); закрытое
                удаляется. Корень — учётка, с которой игрок начал. Одна учётка, открытая двумя путями, это два узла;
    desktop     узел, чей рабочий стол открыт (Workplace.desktop, его читают все приложения);
    terminal    узел, на котором сейчас терминал (Workplace.terminal): команды идут в его сессии. Он может не совпадать с desktop.

rcon растит ребёнка узла терминала и двигает оба указателя, rshell только terminal. Закрытие узла закрывает всё поддерево:
если под ним был рабочий стол, он возвращается на ближайшего предка, где рабочий стол уже был (корень, вход через rcon или
перенос вкладкой), — не на оболочку rshell. Прямой связи между узлами, не родственными по
дереву, нет: путь из C в A идёт через B.

Пока браузер шлёт запросы, сессии рабочего стола и терминала отмечаются активными (seen_at): mark_seen. Подключена — значит
есть в дереве.

Условия входа, их проверяет verdict():
    пароль    нужен, если у записи он задан (хеш);
    ключ      нужен, если у записи есть условие по ключам: игрок предъявляет файл-ключ (-i), в нём
              должны быть ключи, удовлетворяющие условию;
    токен     заменяет и пароль, и ключ; у него свои срок и число использований.
Записи с паролем и ключом требуют и то и другое. Если задан список hid, входить можно только с машин из него.
"""
import time
from datetime import timedelta
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.contrib.auth.hashers import check_password
from django.db.models import F
from django.utils import timezone

from secure.access import satisfied

from machines.access import entry
from machines.models.account import endpoint as endpoint_of
from machines.current import active_session, workplace_for
from machines.models import LoginEvent, Machine, MachineProfile, MachineProfileToken, Session, Workplace
from machines.world import blackout

MAX_DEPTH = 4           # самая длинная цепочка подключений от корня
MAX_NODES = 8           # вкладок (подключений) всего
HOME = "/home"


# ---------- дерево подключений ----------

def session_for(user, profile):
    """Сессия без узла для разовой передачи (xfer по адресу): не сохраняется, в дереве её нет."""
    return Session(user=user, profile=profile)


def _tree(request, create=True):
    """Дерево из базы: {"nodes": {id: {parent, session, cwd, desk, deadline}}, "desktop", "terminal", "root"} — узлы от корня
    рабочего места. create=False: None, если рабочего места ещё нет."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None
    cached = request.__dict__.get("_bridge_tree")
    if cached is not None:                                # за запрос дерево читается из базы один раз
        return cached
    if create:
        place = workplace_for(request)
    else:
        place = request.__dict__.get("_workplace") or Workplace.objects.filter(user=user).first()
        if place is None or place.desktop_id is None or place.terminal_id is None:
            return None
    rows = {str(row.pk): row for row in Session.objects.filter(user=user).select_related("profile__machine").order_by("pk")}
    for row in rows.values():
        row.user = user                                   # тот же игрок: без запроса на каждую сессию
    node = str(place.desktop_id)
    while node in rows and rows[node].parent_id is not None:
        node = str(rows[node].parent_id)
    if node not in rows or str(place.terminal_id) not in rows:
        if not create:
            return None
        Workplace.objects.filter(pk=place.pk).update(desktop=None, terminal=None)
        request.__dict__.pop("_active_session", None)
        request.__dict__.pop("_workplace", None)
        return _tree(request, create)
    root, nodes = node, {}
    frontier = [root]
    while frontier:                                       # только поддерево корня: прочие строки игрока не трогаем
        key = frontier.pop()
        row = rows[key]
        nodes[key] = {"parent": str(row.parent_id) if row.parent_id else None, "session": row.pk, "cwd": row.cwd or HOME,
                      "desk": row.desk or row.parent_id is None, "deadline": row.deadline}
        frontier += [str(child.pk) for child in rows.values() if child.parent_id == row.pk]
    tree = {"nodes": nodes, "desktop": str(place.desktop_id), "terminal": str(place.terminal_id), "root": root, "_was": set(nodes),
            "_rows": rows}
    request.__dict__["_bridge_tree"] = tree
    return tree


def announce_left(user, rows):
    """Сессии закрыты: событие «вышел» по каждой (для ноды «Сессия: Вход и выход»)."""
    from engine.events import emit

    for row in rows:
        emit("machine.logout", user, machine=row.profile.machine, login=row.profile.login, via=row.via)


def _save(request, tree):
    """Записать дерево: закрытые узлы удаляются, у оставшихся — папка, рабочий стол, срок; указатели рабочего места."""
    gone = [int(key) for key in tree.get("_was", ()) if key not in tree["nodes"]]
    if gone:
        rows = [row for row in (tree.get("_rows") or {}).values() if row.pk in gone]
        Session.objects.filter(user=request.user, pk__in=gone).delete()
        announce_left(request.user, rows)
    for key, node in tree["nodes"].items():
        Session.objects.filter(pk=int(key)).update(cwd=node.get("cwd") or HOME, desk=bool(node.get("desk")), deadline=node.get("deadline"))
    Workplace.objects.filter(user=request.user).update(desktop_id=int(tree["desktop"]), terminal_id=int(tree["terminal"]))
    tree["_was"] = set(tree["nodes"])
    request.__dict__["_bridge_tree"] = tree
    request.__dict__.pop("_active_session", None)         # стол мог переехать
    request.__dict__.pop("_workplace", None)


def _depth_of(tree, node):
    count = 0
    while tree["nodes"][node]["parent"] is not None:
        node = tree["nodes"][node]["parent"]
        count += 1
    return count


def _subtree(tree, node):
    found = [node]
    for key, item in tree["nodes"].items():
        if item["parent"] == node:
            found += _subtree(tree, key)
    return found


def _session_of(request, tree, node):
    found = (tree.get("_rows") or {}).get(node)
    if found is not None:
        return found
    return Session.objects.select_related("profile__machine").filter(pk=tree["nodes"][node]["session"], user=request.user).first()


def depth(request):
    """Глубина рабочего стола: 0 на исходной машине, иначе число подключений до него."""
    tree = _tree(request, create=False)
    return _depth_of(tree, tree["desktop"]) if tree else 0


def node_count(request):
    tree = _tree(request, create=False)
    return len(tree["nodes"]) if tree else 1


def terminal_id(request):
    tree = _tree(request, create=False)
    return tree["terminal"] if tree else ""


def desktop_id(request):
    tree = _tree(request, create=False)
    return tree["desktop"] if tree else ""


def at_root(request):
    """Терминал на корне (своя машина): выходить некуда."""
    tree = _tree(request, create=False)
    return tree is None or tree["terminal"] == tree["root"]


def terminal_session(request):
    """Сессия, на которой сейчас терминал."""
    tree = _tree(request, create=False)
    if tree:
        session = _session_of(request, tree, tree["terminal"])
        if session is not None:
            return session
    return active_session(request)


def tabs(request):
    """Вкладки терминала в порядке открытия: узел, метка login@host, где терминал, где рабочий стол. Пусто, пока подключений нет."""
    tree = _tree(request, create=False)
    if not tree or len(tree["nodes"]) < 2:
        return []
    sessions = {int(key): row for key, row in (tree.get("_rows") or {}).items()}
    missing = [n["session"] for n in tree["nodes"].values() if n["session"] not in sessions]
    sessions.update({item.pk: item for item in Session.objects.select_related("profile__machine").filter(pk__in=missing)})
    rows = []
    for key in sorted(tree["nodes"], key=int):
        item = tree["nodes"][key]
        profile = sessions[item["session"]].profile
        rows.append({
            "id": key,
            "parent": item["parent"],
            "label": f"{profile.login}@{profile.machine.hostname}",
            "terminal": key == tree["terminal"],
            "desktop": key == tree["desktop"],
            "deadline": item.get("deadline"),
            "host": profile.machine.hostname,
            "system": profile.machine.system,
        })
    return rows


# ---------- срок подключения ----------

KICKS_KEY = "bridge_kicks"
WARN_AT = (30, 10)          # за сколько секунд до обрыва терминал предупреждает


def locked_for(user, profile):
    """Сколько секунд запись ещё не принимает игрока после обрыва по сроку (0: принимает)."""
    from django.db.models import Max, Q

    from machines.models import AccountBlock

    until = AccountBlock.objects.filter(Q(user=user) | Q(user__isnull=True), profile=profile, until__gt=timezone.now()).aggregate(top=Max("until"))["top"]
    if until is None:
        return 0
    return max(0, int((until - timezone.now()).total_seconds()) + 1)


SEEN_EVERY = 30            # раз в сколько секунд браузер отмечает, где игрок (для «кто сейчас на машине»)


def mark_seen(request):
    """Игрок здесь: сессии рабочего стола и терминала активны (seen_at), рабочее место — тоже. Не чаще раза в SEEN_EVERY
    секунд на браузер; дерево и сессию не создаёт."""
    from django.core.cache import cache

    key = getattr(request.session, "session_key", None)
    if not key or not getattr(request.user, "is_authenticated", False):
        return
    stamp = f"bridge-seen:{key}"
    if cache.get(stamp):
        return
    place = request.__dict__.get("_workplace") or Workplace.objects.filter(user=request.user).first()
    if place is not None:
        now = timezone.now()
        _unstable(request.user, [pk for pk in (place.desktop_id, place.terminal_id) if pk], now)
        Session.objects.filter(pk__in=[pk for pk in (place.desktop_id, place.terminal_id) if pk], user=request.user).update(seen_at=now)
        Workplace.objects.filter(pk=place.pk).update(seen_at=now)
    cache.set(stamp, 1, SEEN_EVERY)


RESET = "bridge-reset:{}"           # отметка «оборвалось по помехам» у сессии: текст обрыва Connection reset by peer


def _unstable(user, ids, now):
    """Игрок работает со столом и терминалом: на машинах с обрывами подключение может оборваться (machines/world/channel.py)."""
    from django.core.cache import cache

    from machines.world import channel

    rows = Session.objects.filter(pk__in=ids, user=user, parent__isnull=False, profile__machine__drop_pct__gt=0).select_related("profile__machine")
    for row in rows:
        seconds = (now - row.seen_at).total_seconds() if row.seen_at else SEEN_EVERY
        if channel.drops(row.profile.machine, seconds):
            Session.objects.filter(pk=row.pk).update(kick_at=now)
            cache.set(RESET.format(row.pk), 1, 3600)


def request_kick(user, profile):
    """Автор просит выкинуть игрока с учётки: подключение закроется при его следующем запросе (expire). Сколько сессий помечено."""
    return Session.objects.filter(user=user, profile=profile).update(kick_at=timezone.now())


def expire(request, now=None):
    """Закрыть подключения, у которых вышел срок или которые автор попросил закрыть (kick_at): как kick. Возвращает список обрывов
    для показа игроку (они же копятся в сессии, пока их не заберёт take_kicks). Запись с cooldown после обрыва по сроку не
    принимает игрока; после обрыва автором блокировки нет."""
    now = now or time.time()
    kicks = []
    mark_seen(request)
    tree = _tree(request, create=False)
    if tree:
        kicked = set(Session.objects.filter(
            pk__in=[node["session"] for node in tree["nodes"].values() if node["parent"] is not None], kick_at__isnull=False,
        ).values_list("pk", flat=True))
    else:
        kicked = set()
    while True:
        tree = _tree(request, create=False)
        if not tree:
            break
        due = [key for key, node in tree["nodes"].items() if node.get("deadline") and node["deadline"] <= now]
        by_author = [key for key, node in tree["nodes"].items() if node["session"] in kicked and node["parent"] is not None]
        if not due and not by_author:
            break
        node = by_author[0] if by_author else min(due, key=lambda key: tree["nodes"][key]["deadline"])
        closed = close(request, node)
        if closed is None or not closed.sessions:
            break
        left = closed.sessions[0]
        profile = left.profile
        reset = False
        if by_author:
            from django.core.cache import cache

            kicked.discard(left.pk)
            reset = bool(cache.get(RESET.format(left.pk)))
            cache.delete(RESET.format(left.pk))
            entry.record(profile, request.user, LoginEvent.Kind.KICKED, detail="reset" if reset else "studio")
        else:
            lock = entry.lock_seconds_of(profile)
            if lock:
                from machines.models import AccountBlock

                AccountBlock.objects.create(profile=profile, user=request.user, until=timezone.now() + timedelta(seconds=lock), cooldown=True)
        kicks.append({
            "label": f"{profile.login}@{profile.machine.hostname}",
            "host": profile.machine.hostname,
            "system": profile.machine.system,
            "message": "Connection reset by peer" if reset else entry.kick_text_of(profile),
            "blackout": blackout.resolve("kick", profile, "Connection reset by peer" if reset else entry.kick_text_of(profile)),
            "desktop": closed.desktop_moved,
            "cwd": closed.cwd,
        })
    if kicks:
        request.session[KICKS_KEY] = [*request.session.get(KICKS_KEY, []), *kicks]
    return kicks


def remember_cwd(request, cwd):
    """Папка терминала сейчас записывается на узле терминала (нужна, чтобы закрытие другого узла её не потеряло)."""
    tree = _tree(request, create=False)
    if tree:
        tree["nodes"][tree["terminal"]]["cwd"] = cwd or HOME
        Session.objects.filter(pk=int(tree["terminal"])).update(cwd=cwd or HOME)


def take_kicks(request):
    """Обрывы, которые игрок ещё не видел: забирает и очищает."""
    return request.session.pop(KICKS_KEY, [])


def can_open(request):
    """None, если можно открыть ещё подключение от узла терминала, иначе причина отказа."""
    tree = _tree(request)
    if len(tree["nodes"]) >= MAX_NODES or _depth_of(tree, tree["terminal"]) + 1 > MAX_DEPTH:
        return "too many nested sessions"
    return None


def open_child(request, profile, desktop, cwd):
    """Подключение profile от узла терминала. cwd это папка терминала сейчас (вернётся при выходе). desktop: сменить и рабочий стол."""
    tree = _tree(request)
    parent = tree["terminal"]
    tree["nodes"][parent]["cwd"] = cwd
    deadline = time.time() + entry.ttl_of(profile) if entry.ttl_of(profile) else None        # срок подключения с момента входа
    session = Session.objects.create(user=request.user, profile=profile, parent_id=int(parent), via=Session.Via.RCON if desktop else Session.Via.RSHELL,
                                     desk=bool(desktop), cwd=HOME, deadline=deadline, seen_at=timezone.now())
    key = str(session.pk)
    tree["nodes"][key] = {"parent": parent, "session": session.pk, "cwd": HOME, "desk": bool(desktop), "deadline": deadline}
    tree.setdefault("_rows", {})[key] = session
    tree["_was"] = {*tree.get("_was", ()), key}
    tree["terminal"] = key
    if desktop:
        tree["desktop"] = key
    _save(request, tree)
    return session


@dataclass
class Closed:
    sessions: list          # закрытые сессии, первая это закрытый узел
    cwd: str                # папка терминала после закрытия
    desktop_moved: bool     # рабочий стол переехал (сменить его в браузере)


def _desk_above(tree, node):
    """Ближайший к node (включая его) узел, где был рабочий стол: корень, вход через rcon или перенос вкладкой."""
    while tree["nodes"][node]["parent"] is not None and not tree["nodes"][node].get("desk"):
        node = tree["nodes"][node]["parent"]
    return node


def close(request, node=None, cwd=HOME):
    """Закрыть узел (по умолчанию терминальный) со всем поддеревом. None для корня: закрывать нечего.
    Терминал переходит на родителя закрытого узла; рабочий стол под закрытым узлом — туда, где он был выше (не на оболочку)."""
    tree = _tree(request)
    node = node or tree["terminal"]
    if node not in tree["nodes"] or tree["nodes"][node]["parent"] is None:
        return None
    if node == tree["terminal"]:
        tree["nodes"][node]["cwd"] = cwd
    gone = _subtree(tree, node)
    parent = tree["nodes"][node]["parent"]
    sessions = [_session_of(request, tree, key) for key in gone]
    moved = tree["desktop"] in gone
    if tree["terminal"] in gone:
        tree["terminal"] = parent
    if moved:
        tree["desktop"] = _desk_above(tree, parent)
    for key in gone:
        del tree["nodes"][key]
    _save(request, tree)
    fresh = moved and tree["terminal"] == tree["desktop"]
    return Closed([item for item in sessions if item is not None], HOME if fresh else tree["nodes"][tree["terminal"]]["cwd"], moved)


def close_all(request):
    """Закрыть все подключения, вернуться на исходную машину. Возвращает (последняя сессия рабочего стола, рабочий стол сменился)."""
    tree = _tree(request, create=False)
    if not tree or len(tree["nodes"]) < 2:
        return None
    left = _session_of(request, tree, tree["terminal"])
    root = tree["root"]
    moved = tree["desktop"] != root
    _save(request, {"nodes": {root: tree["nodes"][root]}, "desktop": root, "terminal": root, "root": root, "_was": tree["_was"]})
    return left, moved


def focus(request, node, cwd):
    """Терминал на узел node (вкладка), рабочий стол не меняется. cwd это папка терминала сейчас. Возвращает папку узла или None."""
    tree = _tree(request)
    if node not in tree["nodes"]:
        return None
    tree["nodes"][tree["terminal"]]["cwd"] = cwd
    tree["terminal"] = node
    _save(request, tree)
    return tree["nodes"][node]["cwd"]


def terminal_reset(request):
    """Новое окно терминала это новая оболочка на машине рабочего стола."""
    tree = _tree(request, create=False)
    if tree:
        tree["terminal"] = tree["desktop"]
        tree["nodes"][tree["desktop"]]["cwd"] = HOME
        _save(request, tree)


def move_desktop(request, node):
    """Рабочий стол на узел node. False, если такого узла нет или он уже открыт."""
    tree = _tree(request)
    if node not in tree["nodes"] or tree["desktop"] == node:
        return False
    tree["desktop"] = node
    tree["nodes"][node]["desk"] = True
    _save(request, tree)
    return True


def parent_id(request):
    """Родитель узла терминала или None в корне."""
    tree = _tree(request, create=False)
    return tree["nodes"][tree["terminal"]]["parent"] if tree else None


def parent_side(request):
    """Сторона «у себя» для xfer: (сессия родителя узла терминала, его папка) или None в корне."""
    tree = _tree(request, create=False)
    if not tree:
        return None
    parent = tree["nodes"][tree["terminal"]]["parent"]
    if parent is None:
        return None
    session = _session_of(request, tree, parent)
    return (session, tree["nodes"][parent]["cwd"]) if session else None


def find_open(request, login, host):
    """Открытый узел login@host (host это имя машины или её метка) или None. Узел терминала не считается."""
    tree = _tree(request, create=False)
    if not tree:
        return None
    for row in tabs(request):
        if row["id"] != tree["terminal"] and row["label"] == f"{login}@{host}":
            return row["id"]
    return None


def side(request, node):
    """(сессия, папка) узла node: сторона xfer. Папка та, на которой узел оставили (по умолчанию /home)."""
    tree = _tree(request, create=False)
    if not tree or node not in tree["nodes"]:
        return None
    session = _session_of(request, tree, node)
    return (session, tree["nodes"][node]["cwd"]) if session else None


def route_ids(request, source, target):
    """Узлы на пути source -> target по дереву, включая оба конца."""
    tree = _tree(request, create=False)
    if not tree:
        return []
    ups = []
    node = source
    while node is not None:
        ups.append(node)
        node = tree["nodes"][node]["parent"]
    down = []
    node = target
    while node is not None and node not in ups:
        down.append(node)
        node = tree["nodes"][node]["parent"]
    return ups[: ups.index(node) + 1] + down[::-1] if node is not None else ups + down[::-1]


def link_lifetime(request, a, b, now=None):
    """Сколько секунд проживёт связь между узлами a и b: до первого срока любого из них (None: без ограничения)."""
    tree = _tree(request, create=False)
    now = now or time.time()
    limits = [tree["nodes"][key].get("deadline") for key in (a, b) if tree and key in tree["nodes"]]
    limits = [item - now for item in limits if item]
    return max(0.0, min(limits)) if limits else None


def route(request, source, target):
    """Метки узлов на пути source -> target по дереву, включая оба конца."""
    labels = {row["id"]: row["label"] for row in tabs(request)}
    return [labels[key] for key in route_ids(request, source, target) if key in labels]


# ---------- поиск записи ----------

@dataclass
class Resolution:
    profile: MachineProfile | None = None
    error: str = ""          # no_host | maintenance | no_account | closed (на этой точке учётка не слушает или точек нет)
    endpoint: str = ""       # через какую точку входа («14.230», «22.000»)


def parse_endpoint(raw):
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def resolve(host, login, endpoint=None):
    """Учётка login на машине host и точка входа: названная (endpoint — частота или порт) или первая из её точек."""
    machine = Machine.objects.filter(hostname=host).first()
    from machines.world import power

    if machine is None or power.is_down(machine):
        return Resolution(error="no_host")
    if power.in_maintenance(machine):
        return Resolution(error="maintenance")
    profile = MachineProfile.objects.filter(machine=machine, login=login).first()
    if profile is None:
        return Resolution(error="no_account")
    if endpoint is not None:
        return Resolution(profile, endpoint=endpoint_of(endpoint)) if profile.serves(endpoint) else Resolution(profile, "closed")
    if not profile.endpoints:
        return Resolution(profile, "closed")
    return Resolution(profile, endpoint=profile.endpoints[0])


def endpoint_text(profile, value=None):
    """Точка входа для игрока: у Aether «14.230 MHz», у остальных порт «22». value — через какую вошли (пусто — первая)."""
    found = endpoint_of(value) if value not in (None, "") else (profile.endpoints[0] if profile.endpoints else "")
    if not found:
        return ""
    return f"{Decimal(found):.3f} MHz" if profile.machine.system == "AETHER" else str(int(Decimal(found)))


# ---------- условия входа ----------

def password_required(profile):
    return bool(profile.password_hash)


def key_required(profile):
    return bool(profile.key_condition)


def methods(profile):
    """Какие способы входа у записи (для отказа в духе ssh: Permission denied (publickey,password))."""
    return [name for name, needed in (("publickey", key_required(profile)), ("password", password_required(profile))) if needed]


def chain_hosts(request):
    """Имена хостов цепочки мостов от исходной машины игрока до узла терминала включительно."""
    tree = _tree(request)
    if not tree:
        return [active_session(request).profile.machine.hostname]
    names, node = [], tree["terminal"]
    while node is not None:
        session = _session_of(request, tree, node)
        if session is not None:
            names.append(session.profile.machine.hostname or session.profile.machine.name)
        node = tree["nodes"][node]["parent"]
    return names[::-1]


def valid_token(profile, value):
    """Токен записи, если он существует, не просрочен и не исчерпан; иначе None."""
    token = MachineProfileToken.objects.filter(profile=profile, token=value).first()
    if token is None:
        return None
    if token.expires_at and token.expires_at <= timezone.now():
        return None
    if token.max_usage is not None and token.usage >= token.max_usage:
        return None
    return token


def spend_token(token):
    MachineProfileToken.objects.filter(pk=token.pk).update(usage=F("usage") + 1)


def keys_ok(profile, key_slugs):
    return not key_required(profile) or satisfied(profile.key_condition, frozenset(key_slugs))


def password_ok(profile, password):
    return not password_required(profile) or check_password(password or "", profile.password_hash)
