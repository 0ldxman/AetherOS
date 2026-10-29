"""Демонстрационный мир для проверки руками: образ системы, две машины, общий том, ключи, зашифрованный файл и архив.

    python manage.py seed_demo

Команду можно запускать повторно: уже созданное не дублируется. Игрок входит под записью ivan на aether-main (пароль demo).
"""
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction

from filesystem import appfile, filemanager
from filesystem.models import FileFormat, Item, ItemKey, ItemMember, Placement, Volume, VolumeTemplate
from machines.models import Export, Machine, MachineMount, MachineProfile, Place, SystemType


def folder(volume, parent, name):
    found, _ = Placement.objects.get_or_create(volume=volume, parent=parent, name=name, defaults={"kind": Placement.Kind.FOLDER})
    return found


def put(volume, path, slug, body="", **fields):
    """Положить объект (создаётся при первом запуске) в том по пути; недостающие папки создаются."""
    *folders, name = path.strip("/").split("/")
    parent = None
    for part in folders:
        parent = folder(volume, parent, part)
    item, _ = Item.objects.get_or_create(slug=slug, defaults={"name": name, "body": body, **fields})
    Placement.objects.get_or_create(volume=volume, parent=parent, name=name, defaults={"kind": Placement.Kind.ITEM, "item": item})
    return item


def mount(machine, volume, path, order=0):
    MachineMount.objects.get_or_create(machine=machine, volume=volume, mount_path=path, defaults={"order": order})


class Command(BaseCommand):
    help = "Создаёт демонстрационный мир (машины, тома, объекты, ключи)."

    @transaction.atomic
    def handle(self, *args, **options):
        FileFormat.objects.get_or_create(
            name="log", defaults={"title": "LOG authentication log", "extension": ".log", "kind": "text", "template": "{body}", "content": "none"},
        )
        FileFormat.objects.get_or_create(
            name="app", defaults={"title": "APP application", "extension": ".app", "kind": "text", "template": "{body}", "content": "text"},
        )
        FileFormat.objects.update_or_create(
            name="key", defaults={"title": "Access key", "extension": ".key", "kind": "text", "template": "{body}", "content": "text"},
        )
        system = SystemType.objects.get(code="AETHER")

        # образ системы: общий для всех машин Aether
        base, fresh = Volume.objects.get_or_create(slug="aether-base", defaults={"name": "Aether system disk", "label": "Образ Aether"})
        if fresh:
            filemanager.apply_template(base, VolumeTemplate.objects.get(name="Unix-подобная система"))
        put(base, "etc/hosts", "demo-hosts", "127.0.0.1 localhost\n10.0.0.2 aether-core\n")
        put(base, "etc/motd", "demo-motd", "Welcome to Aether.\n")
        put(base, "var/log/syslog", "demo-syslog", "boot ok\n")
        put(base, "var/log/auth.log", "demo-auth", format="log", name="auth")

        # рабочий стол: файлы приложений в общем месте desktop системы
        Place.objects.update_or_create(system_type=system, name="desktop", defaults={"path": "/etc/desktop"})
        for slug, label, glyph, path, suffix in (
            ("app-console", "console", ">_", "/apps/terminal/", ".sh"),
            ("app-intercom", "intercom", "@", "/apps/mail/", ".conn"),
            ("app-aether", "aether", "W", "/apps/wiki/", ".db"),
            ("app-world", "world", "M", "/apps/map/", ".map"),
        ):
            volumes = ("aether-core:/srv/harbor as Harbor user=reader",) if label == "aether" else ()       # вики подключает архив порта
            put(base, f"etc/desktop/{label}.app", slug, appfile.render(label, glyph, path, suffix, volumes=volumes), format="app")

        put(base, "etc/desktop/readme.txt", "demo-readme", "Welcome. Files on the desktop open by their kind.\n")

        # ключи
        alpha = Item.objects.get_or_create(slug="alpha", defaults={"name": "Alpha key", "format": "key"})[0]
        Item.objects.get_or_create(slug="harbor-pass", defaults={"name": "Harbor pass", "format": "key"})

        # общий том, который хостит aether-core
        harbor, _ = Volume.objects.get_or_create(slug="harbor", defaults={"name": "Harbor archive", "label": "Архив порта"})
        put(harbor, "ports/manifest.txt", "demo-manifest", "Shipment 7 left at dawn.\n")
        put(harbor, "ports/shipment-7.doc", "demo-shipment", "Shipment 7 left at dawn.\n\nThe crates were unmarked.", format="doc", name="Shipment 7")

        core, _ = Machine.objects.get_or_create(hostname="aether-core", defaults={"name": "Core", "system": system.code})
        mount(core, base, "/", 0)
        mount(core, harbor, "/srv/harbor", 0)

        main, _ = Machine.objects.get_or_create(hostname="aether-main", defaults={"name": "Main", "system": system.code})
        own, _ = Volume.objects.get_or_create(slug="aether-main-own", defaults={"label": "Отличия aether-main"})
        mount(main, base, "/", 0)
        mount(main, own, "/", 1)
        reader, _ = MachineProfile.objects.get_or_create(machine=core, login="reader", defaults={"name": "Reader", "freq": 7.5})
        Export.objects.get_or_create(machine=core, path="/srv/harbor")        # core отдаёт архив порта по сети
        MachineMount.objects.get_or_create(                                   # main подключает его под записью reader хоста
            machine=main, mode="remote", host=core, host_path="/srv/harbor", mount_path="/mnt/harbor", defaults={"account": reader},
        )

        MachineProfile.objects.get_or_create(
            machine=main, login="ivan", defaults={"name": "Ivan", "freq": 14.23, "password_hash": make_password("demo")},
        )

        # отличия aether-main поверх образа
        if not Placement.objects.filter(volume=own, kind=Placement.Kind.WHITEOUT).exists():
            etc = folder(own, None, "etc")
            Placement.objects.create(volume=own, parent=etc, kind=Placement.Kind.WHITEOUT, name="motd")      # приветствия здесь нет
        put(own, "etc/hosts", "main-hosts", "127.0.0.1 localhost\n10.0.0.2 aether-core\n10.0.0.9 aether-deep\n")

        put(own, "home/ivan/notes.txt", "ivan-notes", "Door code is in the report.\n")
        report = put(own, "home/ivan/report.rec", "ivan-report", "Cargo manifest altered.\n\nRef A-113.\n", format="rec")
        ItemKey.objects.get_or_create(item=report, key=alpha)                       # ключ лежит в байтах отчёта (kex)
        put(own, "home/ivan/door.bin", "ivan-door", state="> encrypted hunter2 attempts=3", size=2048)

        pack = put(own, "home/ivan/pack.zip", "ivan-pack", state="")                # архив: объект с членами
        for path, slug, body in (("README.txt", "pack-readme", "Open me.\n"), ("notes/a.txt", "pack-a", "Note A.\n")):
            member, _ = Item.objects.get_or_create(slug=slug, defaults={"name": path.rsplit("/", 1)[-1], "body": body})
            ItemMember.objects.get_or_create(archive=pack, path=path, defaults={"item": member})
        inner, _ = Item.objects.get_or_create(slug="pack-inner", defaults={"name": "inner.7z", "state": "> encrypted vault"})
        ItemMember.objects.get_or_create(archive=pack, path="inner.7z", defaults={"item": inner})
        secret, _ = Item.objects.get_or_create(slug="pack-secret", defaults={"name": "key.txt", "body": "the vault key\n"})
        ItemMember.objects.get_or_create(archive=inner, path="key.txt", defaults={"item": secret})

        self.stdout.write(self.style.SUCCESS(
            "demo ready: machines aether-main (login ivan, password demo) and aether-core; "
            f"{Item.objects.count()} objects, {Volume.objects.count()} volumes"
        ))
