"""Права файлов, привилегии и команды perm и own.

Запуск: python manage.py test filesystem.test_rights
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.models import Placement
from filesystem.testing import make_app, make_file
from machines.models import Group, Machine, MachineProfile


def secure(made, owner="", group="", mode=""):
    Placement.objects.filter(pk=made.placement.pk).update(owner=owner, group=group, mode=mode)
    return made


@override_settings(FORCE_SCRIPT_NAME=None)
class RightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1)
        MachineProfile.objects.create(machine=cls.main, login="admin", name="Admin", freq=2)
        secure(make_file(cls.main, "/srv/secret.txt", body="the plan"), "root", "", "600")
        secure(make_file(cls.main, "/srv/shared.txt", body="for staff"), "root", "staff", "640")
        secure(make_file(cls.main, "/srv/mine.txt", body="mine"), "ivan", "", "644")
        make_file(cls.main, "/srv/open.txt", body="open to all")
        make_file(cls.main, "/home/admin/diary.txt", body="private")
        make_file(cls.main, "/home/ivan/own.txt", body="ivan's")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def run_command(self, text):
        response = self.client.post(reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json")
        return json.loads(response.content)

    def output(self, text):
        return self.run_command(text)["output"]

    def test_a_file_without_rights_is_open_and_with_rights_it_follows_owner_group_others(self):
        self.assertIn("open to all", self.output("txtx /srv/open.txt"))
        self.assertIn("Permission denied", self.output("txtx /srv/secret.txt"))
        self.assertIn("Permission denied", self.output("txtx /srv/shared.txt"))            # группа staff, ivan не в ней
        self.assertIn("mine", self.output("txtx /srv/mine.txt"))

    def test_a_group_member_reads_through_the_group_digit(self):
        self.profile.groups = ["staff"]
        self.profile.save()
        Group.objects.create(machine=self.main, name="staff", privileges=[])
        self.assertIn("for staff", self.output("txtx /srv/shared.txt"))

    def test_ls_shows_the_rights_and_hides_nothing_from_a_reader_of_the_folder(self):
        listing = self.output("ls -l /srv")
        self.assertIn("-rw------- root -  secret.txt", listing)
        self.assertIn("-rw-r--r-- ivan -  mine.txt", listing)
        self.assertIn("-rwxrwxrwx - -  open.txt", listing)

    def test_root_and_the_backup_privilege_read_through_the_rights_but_backup_does_not_write(self):
        Group.objects.create(machine=self.main, name="users", privileges=["bridge", "transfer"], everyone=True)
        Group.objects.create(machine=self.main, name="keeper", privileges=["backup"])
        self.profile.groups = ["keeper"]
        self.profile.save()
        self.assertIn("the plan", self.output("txtx /srv/secret.txt"))
        secure(make_file(self.main, "/vault", directory=True), "root", "", "755")
        self.assertIn("Permission denied", self.output("cp /srv/open.txt /vault/copy.txt"))
        self.profile.groups, self.profile.root = [], True
        self.profile.save()
        self.assertIn("the plan", self.output("txtx /srv/secret.txt"))
        self.assertEqual(self.run_command("cp /srv/open.txt /vault/copy.txt")["exit_code"], 0)

    def test_the_home_of_another_record_is_closed_by_default_and_ones_own_is_not(self):
        self.assertIn("Permission denied", self.output("ls /home/admin"))
        self.assertIn("Permission denied", self.output("txtx /home/admin/diary.txt"))
        self.assertIn("own.txt", self.output("ls /home/ivan"))

    def test_writing_needs_the_right_on_the_folder_or_the_file(self):
        secure(make_file(self.main, "/vault", directory=True), "root", "", "755")
        make_file(self.main, "/vault/ledger.txt", body="x")
        self.assertIn("Permission denied", self.output("cp /srv/open.txt /vault/copy.txt"))
        self.assertIn("Permission denied", self.output("del -f /vault/ledger.txt"))
        self.assertEqual(self.run_command("cp /srv/open.txt /home/ivan/copy.txt")["exit_code"], 0)

    def test_a_copy_belongs_to_the_one_who_made_it_and_a_move_keeps_the_owner(self):
        self.run_command("cp /srv/mine.txt /home/ivan/c.txt")
        self.assertIn("-rw-r--r-- ivan -  c.txt", self.output("ls -l /home/ivan"))
        self.run_command("mv /srv/mine.txt /home/ivan/m.txt")
        self.assertIn("ivan -  m.txt", self.output("ls -l /home/ivan"))

    def test_perm_is_for_the_owner_and_own_needs_the_privilege(self):
        self.assertEqual(self.run_command("perm 600 /srv/mine.txt")["exit_code"], 0)
        self.assertIn("-rw------- ivan", self.output("ls -l /srv/mine.txt"))
        self.assertIn("Operation not permitted", self.output("perm 777 /srv/secret.txt"))
        self.assertIn("Operation not permitted", self.output("own ivan /srv/secret.txt"))
        Group.objects.create(machine=self.main, name="users", privileges=["bridge", "transfer"], everyone=True)
        Group.objects.create(machine=self.main, name="owners", privileges=["chown"])
        self.profile.groups = ["owners"]
        self.profile.save()
        self.assertEqual(self.run_command("own admin:staff /srv/mine.txt")["exit_code"], 0)
        self.assertIn("admin staff", self.output("ls -l /srv/mine.txt"))
        self.assertIn("invalid user", self.output("own nobody /srv/mine.txt"))
        self.assertEqual(self.run_command("perm 12 /srv/mine.txt")["exit_code"], 2)

    def test_the_bridge_and_the_transfer_need_their_privileges(self):
        Group.objects.create(machine=self.main, name="users", disabled=True)
        self.assertIn("Operation not permitted", self.output("rshell admin@aether-main"))
        self.assertIn("Operation not permitted", self.output("xfer /srv/open.txt admin@aether-main:/tmp"))
        self.assertIn("Operation not permitted", self.output("nget example.com/x"))


@override_settings(FORCE_SCRIPT_NAME=None)
class FolderRightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1)
        cls.folder = make_file(cls.main, "/work", directory=True)
        make_file(cls.main, "/work/a.txt", body="a")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def run_command(self, text):
        response = self.client.post(reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json")
        return json.loads(response.content)

    def test_a_folder_gets_its_rights_from_perm_and_they_decide_listing_and_creating(self):
        self.assertEqual(self.run_command("perm 555 /work")["exit_code"], 0)
        self.assertIn("dr-xr-xr-x", self.run_command("ls -l /")["output"])
        self.assertIn("Permission denied", self.run_command("cp /work/a.txt /work/b.txt")["output"])
        self.assertIn("Permission denied", self.run_command("del -f /work/a.txt")["output"])
        self.run_command("perm 755 /work")                                               # тот, кто задал права, их владелец
        self.assertEqual(self.run_command("cp /work/a.txt /work/b.txt")["exit_code"], 0)

    def test_a_folder_without_the_right_to_enter_closes_what_is_in_it(self):
        Placement.objects.filter(pk=self.folder.placement.pk).update(owner="root", mode="700")
        self.assertIn("Permission denied", self.run_command("ls /work")["output"])
        self.assertIn("Permission denied", self.run_command("txtx /work/a.txt")["output"])
        self.assertIn("Permission denied", self.run_command("cd /work")["output"])
        self.assertIn("Operation not permitted", self.run_command("perm 777 /work")["output"])
