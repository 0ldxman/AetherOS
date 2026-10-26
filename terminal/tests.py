"""Терминал: безымянный игрок видит окно, но команды отвечают ошибкой авторизации.

Запуск: python manage.py test terminal
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from machines.models import Machine, MachineApp
from users.aether_auth import AUTH_REQUIRED


@override_settings(FORCE_SCRIPT_NAME=None)
class AnonymousTerminalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")
        MachineApp.objects.create(machine=cls.null, label="console", glyph=">_", path="/apps/terminal/")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def witness(self):
        session = self.client.session
        session["guest"] = True
        session.save()

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        ok = response["Content-Type"].startswith("application/json")
        return response, (json.loads(response.content) if ok else None)

    def test_the_window_opens_for_a_witness(self):
        self.witness()
        response = self.client.get(reverse("terminal:index"))
        self.assertContains(response, "aether-null")

    def test_every_command_answers_with_the_authorization_error_in_the_terminal(self):
        self.witness()
        for command in ("ls", "cnt /home/readme", "whoami", ""):
            response, data = self.run_command(command)
            self.assertEqual(response.status_code, 200, command)           # ошибка внутри терминала, а не редирект
            self.assertEqual(data["exit_code"], 1)
            self.assertIn(AUTH_REQUIRED, data["output"])
            self.assertIsNone(data["window"])
            self.assertEqual(data["hostname"], "aether-null")

    def test_nothing_is_executed_for_a_witness(self):
        from filesystem.models import SessionFile

        self.witness()
        self.run_command("ls")
        self.assertEqual(SessionFile.objects.count(), 0)

    def test_a_visitor_who_is_not_connected_anywhere_is_refused(self):
        self.assertEqual(self.client.get(reverse("terminal:index")).status_code, 403)
        self.assertEqual(self.run_command("ls")[0].status_code, 403)

    def test_the_machine_needs_the_console_icon(self):
        MachineApp.objects.all().delete()
        self.witness()
        self.assertEqual(self.client.get(reverse("terminal:index")).status_code, 403)

    def test_a_signed_in_player_still_gets_a_real_terminal(self):
        user = get_user_model().objects.create_user("ivan", password="pw")
        main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=main, label="console", glyph=">_", path="/apps/terminal/")
        self.client.force_login(user)
        response, data = self.run_command("pwd")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(AUTH_REQUIRED, data["output"])
        self.assertEqual(data["hostname"], "aether-main")


@override_settings(FORCE_SCRIPT_NAME=None)
class TerminalSceneTests(TestCase):
    """Сцены терминала: работа команды играет до ответа, приветствие приходит со страницей."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.models import MachineFile
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        MachineFile.objects.create(machine=cls.main, path="/home/door.bin", state="> encrypted hunter2 attempts=3")
        MachineFile.objects.create(machine=cls.main, path="/home/note.txt", state="> base64")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

    def ops(self, scene):
        return [step["op"] for step in scene]

    def test_a_wrong_password_plays_the_work_and_ends_with_a_failure(self):
        data = self.run_command("cph /home/door.bin nope")
        self.assertEqual(data["exit_code"], 1)
        self.assertIn("bar", self.ops(data["scene"]))
        failed = [step for step in data["scene"] if step["op"] == "dots"]
        self.assertEqual(failed[-1]["status"], "FAIL")
        self.assertIn("wrong", data["output"])                # текст ответа остаётся

    def test_the_right_password_ends_with_success(self):
        data = self.run_command("cph /home/door.bin hunter2")
        self.assertEqual(data["exit_code"], 0)
        done = [step for step in data["scene"] if step["op"] == "dots"]
        self.assertEqual(done[-1]["status"], "OK")
        self.assertIn("decrypted", data["output"])

    def test_commands_without_work_have_no_scene(self):
        self.assertIsNone(self.run_command("pwd")["scene"])
        self.assertIsNone(self.run_command("cph /home/missing.bin x")["scene"])      # ошибка до начала работы
        self.assertIsNone(self.run_command("cph")["scene"])

    def test_the_window_opens_with_a_greeting_scene(self):
        page = self.client.get(reverse("terminal:index")).content.decode()
        self.assertIn('id="terminal-greeting"', page)
        self.assertIn("aether-shell", page)
        self.assertIn("ui/console.js", page)

    def test_the_greeting_is_the_full_node_welcome(self):
        page = self.client.get(reverse("terminal:index")).content.decode()
        for part in ("System information", "Link load", "Standalone mode", "Type "):
            self.assertIn(part, page)
        self.assertNotIn('"op":"read"', page.replace(" ", ""))             # без паузы на чтение: окно открывается быстро

    def test_clear_asks_the_screen_to_wipe(self):
        data = self.run_command("clear")
        self.assertTrue(data["clear"])
        self.assertEqual((data["output"], data["exit_code"]), ("", 0))
        self.assertFalse(self.run_command("pwd")["clear"])
        self.assertEqual(self.run_command("clear now")["exit_code"], 2)
