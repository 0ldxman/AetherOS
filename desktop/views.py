from django.shortcuts import render
from django.urls import reverse

from django.shortcuts import redirect, render
from django.urls import get_script_prefix

from secure.access import satisfied

from machines.current import current_machine, visible_apps

# Create your views here.

APPS = [
    {
        "id": "wiki",
        "label": "aether",
        "glyph": "W",
        "suffix": ".db",
        "url_name": "wiki:home",
    },
    {
        "id": "mail",
        "label": "intercom",
        "glyph": "@",
        "suffix": ".conn",
        "url_name": "sessions",
    },
    {
        "id": "terminal",
        "label": "console",
        "glyph": ">_",
        "suffix": ".sh",
        "url_name": "sessions",
    },
    {
        "id": "sessions",
        "label": "sessions",
        "glyph": "S",
        "suffix": ".mon",
        "url_name": "sessions",
    },
    {
        "id": "map",
        "label": "world",
        "glyph": "M",
        "suffix": ".map",
        "url_name": "map:index",
    },
]

def desktop(request):
    machine = current_machine(request)

    if machine is None:
        return redirect("boot")

    prefix = get_script_prefix().rstrip("/")

    apps = [
        {
            "id": app.pk,
            "label": app.label,
            "glyph": app.glyph,
            "suffix": app.suffix,
            "url": prefix + app.path,
        }
        for app in visible_apps(request, machine)
    ]

    return render(request, "desktop/desktop.html", {
        "machine_name": machine.hostname,
        "apps": apps,
    })

def boot(request):
    return render(request, "boot/boot.html")