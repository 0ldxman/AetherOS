import json

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from machines.current import active_session, current_machine
from users.aether_auth import AUTH_REQUIRED, is_player
from terminal.engine.context import DEFAULT_CWD
from terminal.engine.executor import TerminalExecutor

# Ключ в Django-сессии: текущая папка открытого окна терминала.
# Хранится на сервере, браузер не может её подменить.
CWD_KEY = "terminal_cwd"


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

    source = payload.get("command", "")

    if not isinstance(source, str) or len(source) > 4096:
        return JsonResponse(
            {"error": "Invalid command"},
            status=400,
        )

    session = active_session(request)

    cwd = request.session.get(CWD_KEY, DEFAULT_CWD)

    result, new_cwd = TerminalExecutor().execute(
        session=session,
        source=source,
        cwd=cwd,
    )

    if new_cwd != cwd:
        request.session[CWD_KEY] = new_cwd

    return JsonResponse({
        "output": result.output,
        "exit_code": result.exit_code,
        "window": result.window,
        "cwd": new_cwd,
        "hostname": session.profile.machine.hostname,
    })


def terminal_page(request):
    if is_player(request):
        hostname = active_session(request).profile.machine.hostname
    else:
        machine = current_machine(request)

        if machine is None:
            raise PermissionDenied

        hostname = machine.hostname

    # Каждое открытие окна начинается с /home, как новая оболочка.
    request.session[CWD_KEY] = DEFAULT_CWD

    return render(
        request,
        "terminal.html",
        {
            "hostname": hostname,
            "cwd": DEFAULT_CWD,
        },
    )