from django.shortcuts import render
from django.urls import reverse

# Create your views here.

APPS = [
    {
        "id": "wiki",
        "label": "aether",
        "glyph": "W",
        "suffix": ".db",
        "url_name": "sessions",
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
]

def desktop(request):
    apps = []

    for app in APPS:
        item = app.copy()
        item["url"] = reverse(app["url_name"])
        apps.append(item)

    return render(request, "desktop/desktop.html", {
        "machine_name": "aether-anon",
        "apps": apps,
    })

def boot(request):
    return render(request, "boot/boot.html")