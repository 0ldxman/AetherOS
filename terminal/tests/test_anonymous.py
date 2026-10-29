"""Терминал: безымянный игрок видит окно, но команды отвечают ошибкой авторизации.

Запуск: python manage.py test terminal.tests.test_anonymous
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import make_app, remove_apps
from machines.models import Machine
from users.aether_auth import AUTH_REQUIRED


@override_settings(FORCE_SCRIPT_NAME=None)
class AnonymousTerminalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")
        make_app(cls.null, label="console", glyph=">_", path="/apps/terminal/")

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
        from filesystem.models import PlayerFile

        self.witness()
        self.run_command("ls")
        self.assertEqual(PlayerFile.objects.count(), 0)

    def test_a_visitor_who_is_not_connected_anywhere_is_refused(self):
        self.assertEqual(self.client.get(reverse("terminal:index")).status_code, 403)
        self.assertEqual(self.run_command("ls")[0].status_code, 403)

    def test_the_machine_needs_the_console_icon(self):
        remove_apps()
        self.witness()
        self.assertEqual(self.client.get(reverse("terminal:index")).status_code, 403)

    def test_a_signed_in_player_still_gets_a_real_terminal(self):
        user = get_user_model().objects.create_user("ivan", password="pw")
        main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(main, label="console", glyph=">_", path="/apps/terminal/")
        self.client.force_login(user)
        response, data = self.run_command("pwd")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(AUTH_REQUIRED, data["output"])
        self.assertEqual(data["hostname"], "aether-main")
