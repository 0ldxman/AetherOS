"""edt: правка текста файла в слое игрока.

Запуск: python manage.py test filesystem.tests.test_edit
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.models import Item, Placement
from filesystem.testing import make_app, make_file
from machines.models import Machine, MachineProfile
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class EditTests(TerminalClient, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1)
        cls.note = make_file(cls.main, "/home/ivan/note.txt", body="first")
        make_file(cls.main, "/home/ivan/memo.rec", body="memo text", format="rec")
        Item.objects.filter(pk=make_file(cls.main, "/home/ivan/photo.png").item.pk).update(url="https://example.com/p.png", body="")
        make_file(cls.main, "/home/ivan/vault.txt", body="locked", state="> encrypted hunter2")
        locked = make_file(cls.main, "/home/ivan/readonly.txt", body="fixed")
        Placement.objects.filter(pk=locked.placement.pk).update(owner="root", mode="644")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def edit_url(self, path):
        return reverse("fsview:edit") + "?path=" + path

    def test_a_text_file_opens_in_the_editor_and_a_save_goes_to_the_layer_of_the_player(self):
        data = self.run_command("edt /home/ivan/note.txt")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn(reverse("fsview:edit"), data["window"]["url"])
        page = self.client.get(self.edit_url("/home/ivan/note.txt"))
        self.assertContains(page, "first")
        saved = self.client.post(self.edit_url("/home/ivan/note.txt"), data=json.dumps({"text": "second"}), content_type="application/json")
        self.assertEqual(saved.json(), {"ok": True})
        self.assertIn("second", self.run_command("txtx /home/ivan/note.txt")["output"])
        self.assertEqual(Item.objects.get(pk=self.note.item.pk).body, "first")             # база не тронута

    def test_an_editable_format_opens_and_other_content_does_not(self):
        self.assertEqual(self.run_command("edt /home/ivan/memo.rec")["exit_code"], 0)
        self.assertIn("not a text file", self.run_command("edt /home/ivan/photo.png")["output"])
        self.assertIn("Is a directory", self.run_command("edt /home/ivan")["output"])
        self.assertEqual(self.run_command("edt /home/ivan/nothing")["exit_code"], 2)

    def test_a_locked_file_and_a_file_without_the_right_to_write_do_not_open(self):
        self.assertIn("content is locked", self.run_command("edt /home/ivan/vault.txt")["output"])
        self.assertIn("Permission denied", self.run_command("edt /home/ivan/readonly.txt")["output"])
        saved = self.client.post(self.edit_url("/home/ivan/readonly.txt"), data=json.dumps({"text": "x"}), content_type="application/json")
        self.assertEqual(saved.status_code, 403)

    def test_a_bad_save_is_refused(self):
        saved = self.client.post(self.edit_url("/home/ivan/note.txt"), data=json.dumps({"text": 5}), content_type="application/json")
        self.assertEqual(saved.status_code, 400)
