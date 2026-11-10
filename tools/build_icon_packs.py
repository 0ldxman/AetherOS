"""Паки иконок приложений: по одному на стиль ОС, из наборов Iconify (npm @iconify-json/*), в static/ui/icons/<стиль>/<имя>.svg.

Запуск (наборы ставятся во временный каталог, в проект они не попадают):
    mkdir /tmp/icons && cd /tmp/icons && npm init -y && npm i @iconify-json/lucide @iconify-json/fluent @iconify-json/ph \\
        @iconify-json/pixelarticons @iconify-json/carbon @iconify-json/tabler
    .venv/bin/python tools/build_icon_packs.py /tmp/icons/node_modules/@iconify-json

Имена иконок общие для всех стилей (desktop/icons.py): у каждого стиля свой набор, выбранный под его вид. Стиль tui рисует текстовые значки,
glitched берёт набор aether. Лицензии наборов пишутся рядом (static/ui/icons/LICENSES.md).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "ui" / "icons"

# имя иконки -> имя в наборе; набор у каждого стиля свой
PACKS = {
    "aether": ("lucide", {
        "terminal": "terminal", "mail": "mail", "book": "book", "map": "map", "folder": "folder", "file": "file", "image": "image", "audio": "music",
        "video": "video", "archive": "archive", "key": "key", "lock": "lock", "settings": "settings", "network": "network", "database": "database",
        "chat": "message-square", "monitor": "monitor", "shield": "shield", "search": "search", "tools": "wrench", "globe": "globe", "camera": "camera",
        "calendar": "calendar", "user": "user", "radio": "radio", "chart": "chart-line", "app": "app-window",
    }),
    "modern": ("fluent", {
        "terminal": "window-dev-tools-24-regular", "mail": "mail-24-regular", "book": "book-24-regular", "map": "map-24-regular", "folder": "folder-24-regular",
        "file": "document-24-regular", "image": "image-24-regular", "audio": "music-note-2-24-regular", "video": "video-24-regular",
        "archive": "archive-24-regular", "key": "key-24-regular", "lock": "lock-closed-24-regular", "settings": "settings-24-regular",
        "network": "wifi-1-24-regular", "database": "database-24-regular", "chat": "chat-24-regular", "monitor": "desktop-24-regular",
        "shield": "shield-24-regular", "search": "search-24-regular", "tools": "wrench-24-regular", "globe": "globe-24-regular",
        "camera": "camera-24-regular", "calendar": "calendar-24-regular", "user": "person-24-regular", "radio": "megaphone-24-regular",
        "chart": "chart-multiple-24-regular", "app": "apps-24-regular",
    }),
    "gnome": ("ph", {
        "terminal": "terminal", "mail": "envelope", "book": "book", "map": "map-trifold", "folder": "folder", "file": "file", "image": "image",
        "audio": "music-note", "video": "video", "archive": "archive", "key": "key", "lock": "lock", "settings": "gear", "network": "network",
        "database": "database", "chat": "chat", "monitor": "monitor", "shield": "shield", "search": "magnifying-glass", "tools": "wrench",
        "globe": "globe", "camera": "camera", "calendar": "calendar", "user": "user", "radio": "radio", "chart": "chart-line", "app": "app-window",
    }),
    "classic": ("pixelarticons", {
        "terminal": "terminal", "mail": "mail", "book": "book", "map": "map", "folder": "folder", "file": "file", "image": "image", "audio": "music",
        "video": "video", "archive": "archive", "key": "key", "lock": "lock", "settings": "gear", "network": "wifi", "database": "server",
        "chat": "chat", "monitor": "monitor", "shield": "shield", "search": "search", "tools": "tools", "globe": "globe", "camera": "camera",
        "calendar": "calendar", "user": "user", "radio": "radio", "chart": "chart-line", "app": "grid",
    }),
    "phosphor": ("carbon", {
        "terminal": "terminal", "mail": "email", "book": "book", "map": "map", "folder": "folder", "file": "document", "image": "image", "audio": "music",
        "video": "video", "archive": "archive", "key": "key", "lock": "locked", "settings": "settings", "network": "network-3", "database": "data-base",
        "chat": "chat", "monitor": "screen", "shield": "security", "search": "search", "tools": "tools", "globe": "globe", "camera": "camera",
        "calendar": "calendar", "user": "user", "radio": "radio", "chart": "chart-line", "app": "apps",
    }),
    "workbench": ("tabler", {
        "terminal": "terminal", "mail": "mail", "book": "book", "map": "map", "folder": "folder", "file": "file", "image": "photo", "audio": "music",
        "video": "video", "archive": "archive", "key": "key", "lock": "lock", "settings": "settings", "network": "network", "database": "database",
        "chat": "message", "monitor": "device-desktop", "shield": "shield", "search": "search", "tools": "tool", "globe": "world", "camera": "camera",
        "calendar": "calendar", "user": "user", "radio": "radio", "chart": "chart-line", "app": "apps",
    }),
}
PIXEL = {"pixelarticons", "carbon"}              # ровная пиксельная сетка: без сглаживания


def main(source):
    source = Path(source)
    credits = []
    missing = []
    for style, (pack, names) in PACKS.items():
        data = json.loads((source / pack / "icons.json").read_text())
        info = json.loads((source / pack / "info.json").read_text())
        folder = OUT / style
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.svg"):
            old.unlink()
        for name, icon_id in names.items():
            icon = data["icons"].get(icon_id)
            if icon is None and icon_id in data.get("aliases", {}):
                alias = data["aliases"][icon_id]
                icon = {**data["icons"][alias["parent"]], **{k: v for k, v in alias.items() if k != "parent"}}
            if icon is None:
                missing.append(f"{style}/{name}: {pack}:{icon_id}")
                continue
            width, height = icon.get("width", data.get("width", info.get("height", 24))), icon.get("height", data.get("height", info.get("height", 24)))
            crisp = ' shape-rendering="crispEdges"' if pack in PIXEL else ""
            (folder / f"{name}.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"{crisp}>{icon["body"]}</svg>\n')
        credits.append(f"- **{style}**: {info['name']} ({pack}), {info['license']['title']}, {info['author']['name']}, {info['author'].get('url', '')}")
    (OUT / "LICENSES.md").write_text(
        "# Иконки приложений рабочего стола\n\nНаборы Iconify, по одному на стиль ОС (tools/build_icon_packs.py). Стиль tui рисует текстовые значки, glitched берёт набор aether.\n\n"
        + "\n".join(credits) + "\n"
    )
    if missing:
        print("не нашлись:", *missing, sep="\n  ")
        sys.exit(1)
    print("готово:", ", ".join(PACKS))


if __name__ == "__main__":
    main(sys.argv[1])
