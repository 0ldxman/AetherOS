import json

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from machines.current import active_session, current_machine
from users.aether_auth import AUTH_REQUIRED, is_player
from django.urls import reverse

from machines import bridge
from terminal.engine.commands.bridge import PENDING_KEY, answer_prompt
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

    session = bridge.terminal_session(request)
    cwd = request.session.get(CWD_KEY, DEFAULT_CWD)
    depth_before = bridge.depth(request)
    shell_before = bridge.shell_depth(request)

    if payload.get("cancel"):
        request.session.pop(PENDING_KEY, None)
        result, new_cwd = CommandResult(), cwd
    elif "answer" in payload:
        # ответ на запрос пароля (моста): сам ответ в историю и в вывод не попадает
        text = payload["answer"]
        if not isinstance(text, str) or len(text) > 512:
            return JsonResponse({"error": "Invalid answer"}, status=400)
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
    if bridge.depth(request) != depth_before:
        new_cwd = DEFAULT_CWD      # смена машины начинает новую оболочку
    if bridge.shell_depth(request) > shell_before:
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
    })


def _server_effects(request, session, effects):
    """Эффекты ответа для браузера. kick из хука выполняется здесь, на сервере: игрока выбрасывает на уровень выше
    (или на экран входа, если выше нет), а браузер получает сцену обрыва и смену рабочего стола."""
    from . import bridge_scenes as scenes

    out = []
    for effect in effects or []:
        if effect.get("op") != "kick":
            out.append(effect)
            continue

        host = session.profile.machine.hostname
        system = session.profile.machine.system
        out.append({"op": "play", "scene": scenes.kick_scene(system, host)})
        if bridge.shell_depth(request):
            request.session[CWD_KEY] = bridge.shell_leave(request)[1]
        elif bridge.leave(request):
            request.session[CWD_KEY] = DEFAULT_CWD
            out.append({"op": "switch"})
        else:
            out.append({"op": "lock", "url": reverse("lock")})
    return out


@require_POST
def bridge_close(request):
    """Закрытие окна-туннеля: все мосты закрываются, игрок возвращается на исходную машину."""
    if not is_player(request):
        raise PermissionDenied

    bridge.shell_clear(request)
    bridge.leave(request, all_levels=True)
    request.session[CWD_KEY] = DEFAULT_CWD
    return JsonResponse({"ok": True})


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
    if is_player(request):
        bridge.shell_clear(request)        # новое окно это новая оболочка на машине рабочего стола
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
        },
    )