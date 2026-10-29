"""Справка help.

Запуск: python manage.py test terminal.tests.test_help
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.testing import make_app
from machines.models import Machine
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class HelpTests(TerminalClient, TestCase):
    @classmethod
    def setUpTestData(cls):
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def test_every_command_of_the_system_has_help_text(self):
        from terminal.engine.commands import COMMANDS
        from terminal.engine.commands.help import HELP

        for name in COMMANDS:
            self.assertIn(name, HELP, f"нет справки для {name}")
            summary, synopsis, _ = HELP[name]
            self.assertTrue(summary and synopsis, name)
        for name in HELP:
            self.assertIn(name, COMMANDS, f"справка для несуществующей команды {name}")

    def test_help_speaks_about_the_tools_not_about_the_game(self):
        from terminal.engine.commands.help import HELP

        forbidden = ("layer", "shifted", "puzzle", "game", "real file", "real data", "player", "hint", "solve")
        for name, (summary, synopsis, details) in HELP.items():
            text = " ".join([summary, *synopsis, details]).lower()
            for word in forbidden:
                self.assertNotIn(word, text, f"{name}: справка выдаёт механику ({word})")

    def test_help_lists_the_commands_in_groups(self):
        data = self.run_command("help")
        self.assertEqual(data["exit_code"], 0)
        for name in ("ls", "cnt", "blk", "cvt", "ward", "pak", "kex", "rcon", "help"):
            self.assertIn(name, data["output"])
        self.assertIn("keys and archives:", data["output"])
        self.assertIn("help <command>", data["output"])

    def test_help_about_a_command_shows_usage_and_details(self):
        data = self.run_command("help cvt")
        self.assertEqual(data["exit_code"], 0)
        self.assertIn("cvt ext <file> <out.ext>", data["output"])
        self.assertIn("cvt enc <encoding> <file>", data["output"])
        self.assertIn("usage:", data["output"])
        self.assertEqual(self.run_command("help nothing")["exit_code"], 1)
        self.assertIn("no such command", self.run_command("help nothing")["output"])
        self.assertEqual(self.run_command("help a b")["exit_code"], 2)
