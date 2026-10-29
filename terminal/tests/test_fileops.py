"""cp и mv, домашняя папка записи.

Запуск: python manage.py test terminal.tests.test_fileops
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import make_app, make_file
from machines.models import Machine
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class FileOpsTests(TerminalClient, TestCase):
    """mv и cp: перенос и копирование файлов и папок в сессии."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        for path in ("/home/a.txt", "/home/b.txt", "/home/docs/x.txt", "/home/docs/sub/y.txt", "/home/work/w.txt"):
            make_file(cls.main, path, state="")
        make_file(cls.main, "/home/core.sys", state="", system=True)
        make_file(cls.main, "/home/door.bin", state="> encrypted hunter2")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def ls(self, path="/home"):
        return self.run_command(f"ls {path}")["output"].split()

    def test_a_new_name_follows_the_rules_of_names(self):
        for name in ('"x:y"', '" lead"'):
            data = self.run_command(f"cp /home/a.txt /home/{name}")
            self.assertEqual(data["exit_code"], 1, name)
            self.assertIn("Invalid argument", data["output"])
        self.assertNotIn("x:y", self.run_command("ls /home")["output"])
        self.assertEqual(self.run_command("cp /home/a.txt /home/fine.txt")["exit_code"], 0)

    def test_mv_renames_a_file_and_moves_it_into_a_folder(self):
        self.assertEqual(self.run_command("mv /home/a.txt /home/c.txt")["exit_code"], 0)
        self.assertIn("c.txt", self.ls())
        self.assertNotIn("a.txt", self.ls())
        self.run_command("mv /home/c.txt /home/work")
        self.assertEqual(self.ls("/home/work"), ["c.txt", "w.txt"])

    def test_cp_leaves_the_original_and_keeps_the_layers(self):
        self.assertEqual(self.run_command("cp /home/door.bin /home/door2.bin")["exit_code"], 0)
        self.assertIn("door.bin", self.ls())
        self.assertIn("door2.bin", self.ls())
        self.assertEqual(self.run_command("ward /home/door2.bin hunter2")["exit_code"], 0)
        self.assertIn("Bad session key", self.run_command("ward /home/door.bin nope")["output"])      # у оригинала слой на месте

    def test_a_copy_carries_the_progress_made_before_it(self):
        self.run_command("ward /home/door.bin hunter2")
        self.run_command("cp /home/door.bin /home/open.bin")
        self.assertIn("not encrypted", self.run_command("ward /home/open.bin hunter2")["output"])

    def test_folders_need_r_for_cp_and_move_whole(self):
        self.assertIn("omitting directory", self.run_command("cp /home/docs /home/docs2")["output"])
        self.assertEqual(self.run_command("cp -r /home/docs /home/docs2")["exit_code"], 0)
        self.assertEqual(self.ls("/home/docs2/sub"), ["y.txt"])
        self.assertEqual(self.ls("/home/docs/sub"), ["y.txt"])
        self.run_command("mv /home/docs /home/work")
        self.assertNotIn("docs", self.ls())
        self.assertEqual(self.ls("/home/work/docs/sub"), ["y.txt"])

    def test_several_sources_need_a_folder_as_the_target(self):
        self.assertEqual(self.run_command("mv /home/a.txt /home/b.txt /home/work")["exit_code"], 0)
        self.assertEqual(self.ls("/home/work"), ["a.txt", "b.txt", "w.txt"])
        self.assertIn("is not a directory", self.run_command("cp /home/door.bin /home/core.sys /home/nothing")["output"])

    def test_nothing_is_overwritten_and_errors_are_clear(self):
        self.assertIn("exists", self.run_command("mv /home/a.txt /home/b.txt")["output"])
        self.assertIn("exists", self.run_command("cp /home/a.txt /home/b.txt")["output"])
        self.assertIn("No such file", self.run_command("mv /home/none /home/x")["output"])
        self.assertIn("into itself", self.run_command("cp -r /home/docs /home/docs/sub/copy")["output"])
        self.assertIn("the same", self.run_command("mv /home/a.txt /home/a.txt")["output"])
        self.assertIn("No such file", self.run_command("cp /home/a.txt /nowhere/deep/a.txt")["output"])
        self.assertIn("a.txt", self.ls())                                                   # ничего не пропало
        self.assertEqual(self.run_command("mv /home/a.txt")["exit_code"], 2)

    def test_a_system_file_cannot_move_but_its_copy_is_an_ordinary_file(self):
        self.assertIn("Operation not permitted", self.run_command("mv /home/core.sys /home/work")["output"])
        self.assertEqual(self.run_command("cp /home/core.sys /home/work/core.copy")["exit_code"], 0)
        self.assertEqual(self.run_command("del -f /home/work/core.copy")["exit_code"], 0)   # копию удалить можно
        self.assertIn("Operation not permitted", self.run_command("del -f /home/core.sys")["output"])

    def test_the_trash_is_not_a_source_or_a_target(self):
        self.run_command("del -f /home/a.txt")
        self.assertIn("use rcvr", self.run_command("mv /home/ivan/.trash/a.txt /home/a.txt")["output"])
        self.assertIn("use del", self.run_command("cp /home/b.txt /home/ivan/.trash/b.txt")["output"])


@override_settings(FORCE_SCRIPT_NAME=None)
class HomeFolderTests(TerminalClient, TestCase):
    """Оболочка начинается в домашней папке записи (место home), а если её нет, в /home."""

    @classmethod
    def setUpTestData(cls):
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def test_without_a_home_folder_the_shell_starts_in_home(self):
        page = self.client.get(reverse("terminal:index"))
        self.assertContains(page, 'data-cwd="/home"')
        self.assertContains(page, 'data-home="/home"')

    def test_the_home_folder_of_the_record_is_where_it_starts(self):
        make_file(self.main, "/home/ivan/notes.txt", body="hi")
        page = self.client.get(reverse("terminal:index"))
        self.assertContains(page, 'data-cwd="/home/ivan"')
        self.assertContains(page, "ivan@aether-main:~$")
        self.run_command("cd /")
        data = self.run_command("cd")
        self.assertEqual((data["cwd"], data["home"]), ("/home/ivan", "/home/ivan"))
        self.assertIn("notes.txt", self.run_command("ls")["output"])
