from django.shortcuts import render
from django.urls import reverse


def sessions(request):
    return render(
        request,
        "sessions.html",
        {
            "session_inspector_base": reverse(
                "session_inspector",
                kwargs={"sid": "__SID__"}
            )
        }
    )


def session_inspector(request, sid):
    return render(request, "session_inspector.html", {"sid": sid})