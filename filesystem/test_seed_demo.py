"""Демонстрационный мир: создаётся целиком, повторный запуск ничего не дублирует, и в нём можно играть."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from filesystem.machine_view import MachineView
from filesystem.models import Item, Placement, Volume
from machines.models import Machine, MachineMount, MachineProfile, Session
from terminal.engine.executor import TerminalExecutor


class SeedDemoTests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        self.main = Machine.objects.get(hostname="aether-main")
        self.user = get_user_model().objects.create_user("player", password="x")
        profile = MachineProfile.objects.get(machine=self.main, login="ivan")
        self.session = Session.objects.create(user=self.user, profile=profile)

    def run_command(self, source):
        result, _ = TerminalExecutor().execute(session=self.session, source=source)
        return result

    def test_a_second_run_changes_nothing(self):
        before = (Item.objects.count(), Volume.objects.count(), Placement.objects.count(), MachineMount.objects.count())
        call_command("seed_demo", verbosity=0)
        self.assertEqual(before, (Item.objects.count(), Volume.objects.count(), Placement.objects.count(), MachineMount.objects.count()))

    def test_the_machine_shows_the_image_with_its_own_changes_on_top(self):
        view = MachineView(self.main, None)
        self.assertIn("10.0.0.9", view.get("/etc/hosts").body)                          # перекрыто своим файлом
        self.assertFalse(view.exists("/etc/motd"))                                       # скрыто надгробием
        self.assertTrue(view.exists("/var/log/syslog"))                                  # осталось от образа
        self.assertTrue(view.exists("/mnt/harbor/ports/manifest.txt"))                  # смонтирован общий том

    def test_the_player_can_work_in_it(self):
        self.assertIn("door.bin", self.run_command("ls /home/ivan").output)
        self.assertIn("decrypted", self.run_command("ward /home/ivan/door.bin hunter2").output)
        self.assertIn("pak: extracted 3 files", self.run_command("pak x /home/ivan/pack.zip").output)

    def test_the_archive_lists_its_members_and_the_nested_one_needs_its_password(self):
        listing = self.run_command("pak l /home/ivan/pack.zip").output
        self.assertIn("README.txt", listing)
        self.assertIn("inner.7z", listing)
        self.assertNotIn("key.txt", listing)

    def test_a_player_change_on_the_shared_volume_is_seen_from_the_host(self):
        self.run_command("cp /mnt/harbor/ports/manifest.txt /mnt/harbor/ports/copy.txt")
        core = Machine.objects.get(hostname="aether-core")
        self.assertTrue(MachineView(core, self.user).exists("/srv/harbor/ports/copy.txt"))
        self.assertFalse(MachineView(core, None).exists("/srv/harbor/ports/copy.txt"))      # чужой слой не виден

    def test_the_key_in_the_report_can_be_extracted(self):
        raw = self.run_command("txtx /home/ivan/report.rec").output
        self.assertIn("Keyname: alpha", raw)

    def test_the_wiki_of_the_main_machine_shows_the_harbor_of_the_core(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from machines.current import SESSION_KEY
        from wiki import library

        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {SESSION_KEY: self.session.pk}
        found = library.build(request)
        self.assertEqual([page.title for page in found.pages], ["Shipment 7"])
        self.assertEqual(found.nodes[0].name, "Harbor")
