import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from machines.models import Session
from terminal.engine.executor import TerminalExecutor
from django.shortcuts import render

from machines.current import active_session

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
    cwd = payload.get("cwd", "/home")

    if not isinstance(source, str) or len(source) > 4096:
        return JsonResponse(
            {"error": "Invalid command"},
            status=400,
        )

    if not isinstance(cwd, str) or len(cwd) > 2048:
        return JsonResponse(
            {"error": "Invalid working directory"},
            status=400,
        )

    session = active_session(request)

    result, new_cwd = TerminalExecutor().execute(
        session=session,
        source=source,
        cwd=cwd,
    )

    return JsonResponse({
        "output": result.output,
        "exit_code": result.exit_code,
        "cwd": new_cwd,
        "hostname": session.profile.machine.hostname,
    })


@login_required
def terminal_page(request):
    session = active_session(request)

    return render(
        request,
        "terminal.html",
        {"hostname": session.profile.machine.hostname},
    )