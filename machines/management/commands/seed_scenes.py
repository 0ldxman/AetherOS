"""Загрузить библиотеку сцен из scenes/library/*.scene в базу (слаг = имя файла) и, если просят, назначить загрузку ОС.

    manage.py seed_scenes                  только положить сцены в библиотеку (существующие с тем же слагом обновляются)
    manage.py seed_scenes --bind AETHER    ещё назначить boot и boot-short слотам machine.boot и machine.boot_short этой ОС
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from machines.models import SceneScript, SystemScene, SystemType

LIBRARY = Path(__file__).resolve().parents[3] / "scenes" / "library"
BOOT_SLOTS = {"machine.boot": "boot", "machine.boot_short": "boot-short"}


class Command(BaseCommand):
    help = "Загрузить библиотеку сцен из scenes/library в базу."

    def add_arguments(self, parser):
        parser.add_argument("--bind", metavar="CODE", help="код ОС, которой назначить загрузку из библиотеки")

    def handle(self, *args, **options):
        files = sorted(LIBRARY.glob("*.scene"))
        saved = []
        for path in files:                       # сцены вставляют друг друга: сначала кладём все, потом проверяем все
            script, _ = SceneScript.objects.get_or_create(slug=path.stem)
            script.body, script.title = path.read_text(), script.title or path.stem
            script.save()
            saved.append(script)
        for script in saved:
            script.full_clean()
        self.stdout.write(f"сцен в библиотеке: {len(files)}")
        if options["bind"]:
            system = SystemType.objects.filter(code=options["bind"].upper()).first()
            if system is None:
                raise CommandError(f"нет ОС с кодом {options['bind']}")
            for slot, slug in BOOT_SLOTS.items():
                row = SystemScene.objects.filter(system_type=system, slot=slot).first() or SystemScene(system_type=system, slot=slot)
                row.script = SceneScript.objects.get(slug=slug)
                row.full_clean()
                row.save()
            self.stdout.write(f"загрузка назначена ОС {system.code}")
