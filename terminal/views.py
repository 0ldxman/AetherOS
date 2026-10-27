import json
import re

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from machines.current import active_session, current_machine
from users.aether_auth import AUTH_REQUIRED, is_player
from django.urls import get_script_prefix, reverse

from machines import bridge
from terminal.engine.commands.bridge import PENDING_KEY, answer_prompt
from terminal.engine.commands.trash import CONFIRM_KEY, answer_confirm
from terminal.engine.context import CWD_KEY, DEFAULT_CWD
from terminal.engine.executor import TerminalExecutor
from terminal.engine.result import CommandResult


def _anonymous_answer(request):
    """Безымянный игрок: терминал открыт, но командам он отвечает ошибкой, а не выполняет их."""
    machine = current_machine(request)

    if machine is None:
        raise PermissionDenied

    return JsonResponse({
        "output": f"terminal: access denied: {AUTH_REQUIRED}",
        "exit_code": 1,
        "window": None,
        "cwd": DEFAULT_CWD,
        "hostname": machine.hostname,
    })


def _kicks(request):
    """Обрывы по сроку, которые случились с игроком (и ещё не показаны): для ответа браузеру. Папка терминала подстраивается."""
    from . import bridge_scenes as scenes

    bridge.remember_cwd(request, request.session.get(CWD_KEY, DEFAULT_CWD))
    bridge.expire(request)
    kicks = bridge.take_kicks(request)
    if kicks:
        request.session[CWD_KEY] = kicks[-1]["cwd"]
    return [
        {**item, "message": item["message"] or scenes.default_kick_text(item["system"], item["host"])}
        for item in kicks
    ]


def _tabs(request):
    """Вкладки для браузера: у вкладки со сроком ещё текст предупреждения ({n} подставит браузер)."""
    from . import bridge_scenes as scenes

    rows = bridge.tabs(request)
    for row in rows:
        row["warn"] = scenes.warning_text(row.pop("system"), row["host"]) if row["deadline"] else ""
    return rows


def _clock():
    import time

    return time.time()


@require_POST
def execute(request):
    if not is_player(request):
        return _anonymous_answer(request)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {"error": "Expected a JSON object"},
            status=400,
        )

    kicks = _kicks(request)
    if kicks:
        return _tab_payload(request, {"output": "", "exit_code": 1, "kicks": kicks})       # подключение закончилось до команды

    session = bridge.terminal_session(request)
    cwd = request.session.get(CWD_KEY, DEFAULT_CWD)
    desktop_before = bridge.desktop_id(request)
    nodes_before = bridge.node_count(request)

    if payload.get("cancel"):
        request.session.pop(PENDING_KEY, None)
        request.session.pop(CONFIRM_KEY, None)
        result, new_cwd = CommandResult(), cwd
    elif "answer" in payload:
        # ответ на запрос пароля (моста): сам ответ в историю и в вывод не попадает
        text = payload["answer"]
        if not isinstance(text, str) or len(text) > 512:
            return JsonResponse({"error": "Invalid answer"}, status=400)
        if request.session.get(CONFIRM_KEY):
            result, new_cwd = answer_confirm(request, text, session, cwd)
        else:
            result, new_cwd = answer_prompt(request, text, session, cwd)
    else:
        source = payload.get("command", "")

        if not isinstance(source, str) or len(source) > 4096:
            return JsonResponse(
                {"error": "Invalid command"},
                status=400,
            )

        result, new_cwd = TerminalExecutor().execute(
            session=session,
            source=source,
            cwd=cwd,
            request=request,
        )

    effects = _server_effects(request, session, result.effects)
    if bridge.desktop_id(request) != desktop_before:
        new_cwd = DEFAULT_CWD      # смена рабочего стола начинает новую оболочку
    elif bridge.node_count(request) > nodes_before:
        # вошли в оболочку на другой машине: её приветствие после ответа команды
        greeting = _greeting(request, bridge.terminal_session(request).profile.machine.hostname, mail=False)
        if greeting:
            effects.append({"op": "play", "scene": greeting})

    if new_cwd != cwd:
        request.session[CWD_KEY] = new_cwd

    return JsonResponse({
        "output": result.output,
        "exit_code": result.exit_code,
        "window": result.window,
        "scene": result.scene,
        "clear": result.clear,
        "effects": effects,
        "prompt": result.prompt,
        "cwd": new_cwd,
        "hostname": bridge.terminal_session(request).profile.machine.hostname,
        "login": bridge.terminal_session(request).profile.login,
        "tabs": _tabs(request),
        "now": _clock(),
        "warn_at": bridge.WARN_AT,
    })


def _server_effects(request, session, effects):
    """Эффекты ответа для браузера. kick из хука выполняется здесь, на сервере: игрока выбрасывает на уровень выше
    (или на экран входа, если выше нет), а браузер получает сцену обрыва и смену рабочего стола."""
    from . import bridge_scenes as scenes

    out = []
    for effect in effects or []:
        if effect.get("op") == "open":
            # адрес в хуке внутренний; префикс сайта добавляется здесь, как у обычного cnt
            url = get_script_prefix().rstrip("/") + "/" + effect["url"]
            out.append({**effect, "url": url, "id": "hook-" + re.sub(r"\W+", "-", effect["url"]).strip("-")})
            continue
        if effect.get("op") != "kick":
            out.append(effect)
            continue

        host = session.profile.machine.hostname
        system = session.profile.machine.system
        out.append({"op": "play", "scene": scenes.kick_scene(system, host)})
        closed = bridge.close(request, cwd=request.session.get(CWD_KEY, DEFAULT_CWD))
        if closed is None:
            out.append({"op": "lock", "url": reverse("lock")})
            continue
        request.session[CWD_KEY] = closed.cwd
        if closed.desktop_moved:
            out.append({"op": "switch"})
    return out


@require_POST
def bridge_close(request):
    """Закрытие окна-туннеля: все мосты закрываются, игрок возвращается на исходную машину."""
    if not is_player(request):
        raise PermissionDenied

    bridge.close_all(request)
    request.session[CWD_KEY] = DEFAULT_CWD
    return JsonResponse({"ok": True})


def _tab_payload(request, extra=None):
    session = bridge.terminal_session(request)
    return JsonResponse({
        "cwd": request.session.get(CWD_KEY, DEFAULT_CWD),
        "hostname": session.profile.machine.hostname,
        "login": session.profile.login,
        "tabs": _tabs(request),
        "now": _clock(),
        "warn_at": bridge.WARN_AT,
        **(extra or {}),
    })


def _tab_node(request):
    if not is_player(request):
        raise PermissionDenied
    try:
        node = json.loads(request.body).get("node")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        node = None
    return node if isinstance(node, str) else None


@require_POST
def tick(request):
    """Браузер дошёл до срока подключения: сервер закрывает всё, что вышло, и говорит, что случилось."""
    if not is_player(request):
        raise PermissionDenied
    return _tab_payload(request, {"kicks": _kicks(request)})


@require_POST
def tab_focus(request):
    """Клик по вкладке: терминал работает на другом узле, рабочий стол остаётся."""
    kicks = _kicks(request) if is_player(request) else []
    if kicks:
        return _tab_payload(request, {"kicks": kicks})
    node = _tab_node(request)
    request.session.pop(PENDING_KEY, None)
    request.session.pop(CONFIRM_KEY, None)
    cwd = bridge.focus(request, node, request.session.get(CWD_KEY, DEFAULT_CWD)) if node else None
    if cwd is None:
        return JsonResponse({"error": "No such connection"}, status=404)
    request.session[CWD_KEY] = cwd
    return _tab_payload(request)


@require_POST
def tab_desktop(request):
    """Контекстное меню вкладки: рабочий стол переезжает на её машину."""
    kicks = _kicks(request) if is_player(request) else []
    if kicks:
        return _tab_payload(request, {"kicks": kicks})
    node = _tab_node(request)
    if not node or not bridge.move_desktop(request, node):
        return JsonResponse({"error": "No such connection"}, status=404)
    return _tab_payload(request, {"effects": [{"op": "switch"}]})


@require_POST
def tab_close(request):
    """Контекстное меню вкладки: закрыть подключение со всем, что открыто из него."""
    kicks = _kicks(request) if is_player(request) else []
    if kicks:
        return _tab_payload(request, {"kicks": kicks})
    from . import bridge_scenes as scenes

    node = _tab_node(request)
    closed = bridge.close(request, node, cwd=request.session.get(CWD_KEY, DEFAULT_CWD)) if node else None
    if closed is None:
        return JsonResponse({"error": "No such connection"}, status=404)
    request.session[CWD_KEY] = closed.cwd
    left = closed.sessions[0]
    scene = scenes.disconnect_scene(left.profile.machine.system, left.profile.machine.hostname, cut=closed.desktop_moved)
    return _tab_payload(request, {"scene": scene, "effects": [{"op": "switch"}] if closed.desktop_moved else []})


def prompt_path(cwd):
    """Путь для приглашения, как в Linux: /home это ~, внутри него ~/папка, остальное полным путём."""
    if cwd == DEFAULT_CWD:
        return "~"
    if cwd.startswith(DEFAULT_CWD + "/"):
        return "~" + cwd[len(DEFAULT_CWD):]
    return cwd


def _login(request):
    """Под каким логином игрок в оболочке: логин профиля или имя безымянного игрока."""
    from users.aether_auth import GUEST_LOGIN

    return bridge.terminal_session(request).profile.login if is_player(request) else GUEST_LOGIN


def _greeting(request, hostname, mail=True):
    """Сцена приветствия оболочки (или None, если машину не описать). Почта в ней своя только у рабочего стола."""
    from machines.identity import identity_of
    from machines.models import Machine
    from users.aether_auth import _mail_summary

    from .scenes import greeting_scene

    try:
        return greeting_scene(identity_of(hostname), _login(request), _mail_summary(request) if mail else None)
    except Machine.DoesNotExist:
        return None


def terminal_page(request):
    kicks = _kicks(request) if is_player(request) else []
    if is_player(request):
        bridge.terminal_reset(request)     # новое окно это новая оболочка на машине рабочего стола
        hostname = active_session(request).profile.machine.hostname
    else:
        machine = current_machine(request)

        if machine is None:
            raise PermissionDenied

        hostname = machine.hostname

    # Каждое открытие окна начинается с /home, как новая оболочка.
    request.session[CWD_KEY] = DEFAULT_CWD

    greeting = _greeting(request, hostname)

    return render(
        request,
        "terminal.html",
        {
            "hostname": hostname,
            "login": _login(request),
            "cwd": DEFAULT_CWD,
            "prompt_path": prompt_path(DEFAULT_CWD),
            "greeting": greeting,
            "tabs": _tabs(request) if is_player(request) else [],
            "boot": {"kicks": kicks, "now": _clock(), "warn_at": bridge.WARN_AT},
            "tab_urls": {
                "focus": reverse("terminal:tab_focus"),
                "desktop": reverse("terminal:tab_desktop"),
                "close": reverse("terminal:tab_close"),
                "tick": reverse("terminal:tick"),
            },
        },
    )