import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from machines.current import active_session
from terminal.engine.context import DEFAULT_CWD
from terminal.engine.executor import TerminalExecutor

# Ключ в Django-сессии: текущая папка открытого окна терминала.
# Хранится на сервере, браузер не может её подменить.
CWD_KEY = "terminal_cwd"


@login_required
@require_POST
def execute(request):
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


@login_required
def terminal_page(request):
    session = active_session(request)

    # Каждое открытие окна начинается с /home, как новая оболочка.
    request.session[CWD_KEY] = DEFAULT_CWD

    return render(
        request,
        "terminal.html",
        {
            "hostname": session.profile.machine.hostname,
            "cwd": DEFAULT_CWD,
        },
    )