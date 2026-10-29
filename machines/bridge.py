"""Мост: игрок входит с одной машины на другую из терминала (rcon, rshell).

Состояние живёт в Django-сессии, на сервере, браузер его подменить не может. Это дерево подключений:

    узел        одно подключение: сессия машины (для пары игрок, запись) и родитель, откуда подключились;
                корень это машина, на которой игрок начал. Один и тот же профиль, открытый двумя путями, это два узла;
    desktop     узел, чей рабочий стол открыт (его сессия лежит в machine_session_id и читают все приложения);
    terminal    узел, на котором сейчас терминал: команды идут в его сессии. Он может не совпадать с desktop.

rcon растит ребёнка узла терминала и двигает оба указателя, rshell только terminal. Закрытие узла закрывает всё поддерево:
если под ним был рабочий стол, он возвращается на родителя закрытого узла. Прямой связи между узлами, не родственными по
дереву, нет: путь из C в A идёт через B.

Сессия для пары (игрок, запись) переиспользуется: прогресс по файлам и счётчики попыток остаются между визитами.

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

from machines import entry
from machines.current import SESSION_KEY, active_session
from machines.models import Machine, MachineProfile, MachineProfileToken, Session

TREE_KEY = "bridge_tree"
MAX_DEPTH = 4           # самая длинная цепочка подключений от корня
MAX_NODES = 8           # вкладок (подключений) всего
HOME = "/home"


# ---------- дерево подключений ----------

def session_for(user, profile):
    """Сессия пары (игрок, запись): переиспользуется между визитами, прогресс по файлам остаётся."""
    session = Session.objects.filter(user=user, profile=profile).select_related("profile__machine").order_by("-pk").first()
    if session is None:
        session = Session.objects.create(user=user, profile=profile)
    return session


def _tree(request, create=True):
    """Дерево из сессии Django. Если рабочий стол сменили мимо моста (другим входом), дерево начинается заново."""
    tree = request.session.get(TREE_KEY)
    current = request.session.get(SESSION_KEY)
    if tree is not None:
        node = tree["nodes"].get(tree["desktop"])
        if node is None or (current is not None and node["session"] != current):
            tree = None
    if tree is None:
        if not create:
            return None
        base = active_session(request)
        tree = {"next": 1, "nodes": {"0": {"parent": None, "session": base.pk, "cwd": HOME}}, "desktop": "0", "terminal": "0"}
    return tree


def _save(request, tree):
    request.session[TREE_KEY] = tree
    request.session[SESSION_KEY] = tree["nodes"][tree["desktop"]]["session"]


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
    return tree["terminal"] if tree else "0"


def desktop_id(request):
    tree = _tree(request, create=False)
    return tree["desktop"] if tree else "0"


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
    sessions = {
        item.pk: item
        for item in Session.objects.select_related("profile__machine").filter(pk__in=[n["session"] for n in tree["nodes"].values()])
    }
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
    until = Session.objects.filter(user=user, profile=profile, blocked_until__isnull=False).order_by("-pk").values_list(
        "blocked_until", flat=True
    ).first()
    if until is None:
        return 0
    return max(0, int((until - timezone.now()).total_seconds()) + 1)


def expire(request, now=None):
    """Закрыть подключения, у которых вышел срок: как kick, но по времени. Возвращает список обрывов для показа игроку
    (они же копятся в сессии, пока их не заберёт take_kicks). Запись с cooldown после обрыва не принимает игрока."""
    now = now or time.time()
    kicks = []
    while True:
        tree = _tree(request, create=False)
        if not tree:
            break
        due = [key for key, node in tree["nodes"].items() if node.get("deadline") and node["deadline"] <= now]
        if not due:
            break
        node = min(due, key=lambda key: tree["nodes"][key]["deadline"])
        closed = close(request, node)
        if closed is None or not closed.sessions:
            break
        left = closed.sessions[0]
        profile = left.profile
        lock = entry.lock_seconds_of(profile)
        if lock:
            Session.objects.filter(pk=left.pk).update(blocked_until=timezone.now() + timedelta(seconds=lock))
        kicks.append({
            "label": f"{profile.login}@{profile.machine.hostname}",
            "host": profile.machine.hostname,
            "system": profile.machine.system,
            "message": entry.kick_text_of(profile),
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
        tree["nodes"][tree["terminal"]]["cwd"] = cwd
        request.session[TREE_KEY] = tree


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
    session = session_for(request.user, profile)
    parent = tree["terminal"]
    tree["nodes"][parent]["cwd"] = cwd
    key = str(tree["next"])
    tree["next"] += 1
    tree["nodes"][key] = {
        "parent": parent, "session": session.pk, "cwd": HOME,
        "deadline": time.time() + entry.ttl_of(profile) if entry.ttl_of(profile) else None,        # срок подключения с момента входа
    }
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


def close(request, node=None, cwd=HOME):
    """Закрыть узел (по умолчанию терминальный) со всем поддеревом. None для корня: закрывать нечего.
    Терминал переходит на родителя закрытого узла, рабочий стол под закрытым узлом тоже."""
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
        tree["desktop"] = parent
    for key in gone:
        del tree["nodes"][key]
    _save(request, tree)
    return Closed([item for item in sessions if item is not None], HOME if moved else tree["nodes"][tree["terminal"]]["cwd"], moved)


def close_all(request):
    """Закрыть все подключения, вернуться на исходную машину. Возвращает (последняя сессия рабочего стола, рабочий стол сменился)."""
    tree = _tree(request, create=False)
    if not tree or len(tree["nodes"]) < 2:
        return None
    left = _session_of(request, tree, tree["terminal"])
    moved = tree["desktop"] != "0"
    root = tree["nodes"]["0"]
    _save(request, {"next": 1, "nodes": {"0": root}, "desktop": "0", "terminal": "0"})
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
    error: str = ""          # no_host | no_account | ambiguous | bad_endpoint


def parse_endpoint(raw):
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def resolve(host, login, endpoint=None):
    """Запись login на машине host. endpoint (частота или порт) нужен, если у логина несколько записей."""
    machine = Machine.objects.filter(hostname=host).first()
    if machine is None:
        return Resolution(error="no_host")

    profiles = list(MachineProfile.objects.filter(machine=machine, login=login))
    if endpoint is not None:
        profiles = [p for p in profiles if p.freq == endpoint]
    if not profiles:
        return Resolution(error="no_account")
    if len(profiles) > 1:
        return Resolution(error="ambiguous")
    return Resolution(profiles[0])


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
    tree = _tree(request, create=False)
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
