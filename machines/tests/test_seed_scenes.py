"""seed_scenes кладёт библиотеку сцен в базу, и назначенная ОС загрузка играет то же, что встроенная."""
from django.core.management import call_command
from django.test import TestCase

from machines.models import Machine, SceneScript, SystemScene, SystemType
from machines.world.identity import identity_of
from scenes.boots import aether_boot, boot_scenes
from scenes.tests.test_library import strip


class SeedScenesTests(TestCase):
    def test_the_library_lands_in_the_database_and_binds_the_boot_to_an_os(self):
        SystemType.objects.get_or_create(code="AETHER", defaults={"name": "Aether"})
        Machine.objects.create(name="Main", hostname="aether-main")
        call_command("seed_scenes", stdout=open("/dev/null", "w"))
        self.assertTrue(SceneScript.objects.filter(slug="boot-units").exists())
        self.assertEqual(SystemScene.objects.count(), 0)
        call_command("seed_scenes", "--bind", "aether", stdout=open("/dev/null", "w"))
        self.assertEqual(sorted(SystemScene.objects.values_list("slot", flat=True)), ["machine.boot", "machine.boot_short"])

        ident = identity_of("aether-main")
        shown = boot_scenes(ident, "AETHER")
        self.assertEqual(strip(shown["full"]), strip(aether_boot(ident).to_dict()))
        self.assertEqual(strip(shown["short"]), strip(aether_boot(ident, short=True).to_dict()))
