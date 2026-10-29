"""Файлы со своим текстом автора (без объекта): размещение «файл» и член архива с текстом. Для игрока это обычные файлы.

Запуск: python manage.py test terminal.tests.test_authored
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.machine_view import MachineView
from filesystem.models import FileFormat, Item, ItemMember, Placement
from filesystem.testing import _folder, make_app, root_volume
from machines.models import Machine, MachineProfile
from terminal.testing import TerminalClient

HOSTS = "127.0.0.1 localhost\n10.0.0.2 aether-core\n"


@override_settings(FORCE_SCRIPT_NAME=None)
class AuthoredFileTests(TerminalClient, TestCase):
    @classmethod
    def setUpTestData(cls):
        FileFormat.objects.update_or_create(name="txt", defaults={"extension": ".txt", "kind": "text", "template": "{body}", "content": "text_asset", "editable": True})
        FileFormat.objects.update_or_create(name="zip", defaults={"extension": ".zip", "kind": "zip", "content": "none"})
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1, mail="ivan@aether-main")
        volume = root_volume(cls.main)
        etc = _folder(volume, None, "etc")
        _folder(volume, None, "home")
        cls.hosts = Placement.objects.create(volume=volume, parent=etc, kind="file", name="hosts", content=HOSTS)
        cls.secret = Placement.objects.create(volume=volume, parent=etc, kind="file", name="shadow.txt", content="root:x:0",
                                              state="> encrypted hunter2")
        pack = Item.objects.create(slug="pack", name="pack", format="zip")
        ItemMember.objects.create(archive=pack, path="docs/readme.txt", content="Unpack me, please.")
        Placement.objects.create(volume=volume, parent=_folder(volume, None, "home"), name="pack.zip", item=pack)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def test_the_player_sees_and_reads_it_like_any_file(self):
        self.assertIn("hosts", self.run_command("ls /etc")["output"])
        self.assertIn("10.0.0.2 aether-core", self.run_command("txtx /etc/hosts")["output"])
        self.assertFalse(Item.objects.filter(name="hosts").exists())                        # объекта для него нет

    def test_the_layers_of_the_place_protect_it(self):
        raw = self.run_command("txtx /etc/shadow.txt")["output"]
        self.assertNotIn("root:x:0", raw)

    def test_an_edit_and_a_copy_stay_with_the_player_and_the_author_text_is_kept(self):
        view = MachineView(self.main, self.user)
        view.edit_text("/etc/hosts", HOSTS + "10.0.0.9 trap\n")
        self.assertIn("trap", self.run_command("txtx /etc/hosts")["output"])
        entry = MachineView(self.main, self.user).get("/etc/hosts")
        self.assertEqual((entry.placement, entry.authored), (self.hosts, True))                # место (права, слои) осталось
        self.hosts.refresh_from_db()
        self.assertNotIn("trap", self.hosts.content)                                           # текст автора не тронут
        self.assertEqual(self.run_command("cp /etc/hosts /home/h.txt")["exit_code"], 0)
        self.assertIn("trap", self.run_command("txtx /home/h.txt")["output"])
        other = get_user_model().objects.create_user("anna")
        self.assertNotIn("trap", MachineView(self.main, other).get("/etc/hosts").body)        # правка видна только игроку

    def test_a_text_member_of_an_archive_is_extracted_as_the_players_file(self):
        self.assertIn("readme.txt  18", self.run_command("pak l /home/pack.zip")["output"])
        self.assertEqual(self.run_command("pak x /home/pack.zip")["exit_code"], 0)
        self.assertIn("Unpack me, please.", self.run_command("txtx /home/pack/docs/readme.txt")["output"])

    def test_the_rules_of_the_kinds(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            Placement(volume=self.hosts.volume, kind="folder", name="x", content="text").full_clean()
        with self.assertRaises(ValidationError):
            ItemMember(archive=Item.objects.get(slug="pack"), path="a.txt", item=Item.objects.get(slug="pack"), content="t").full_clean()
