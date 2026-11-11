"""Диалекты путей в терминале: ввод и вывод путей по обычаю ОС машины (VMS, мейнфрейм, Windows).

Запуск: python manage.py test terminal.tests.test_dialects
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import make_app, make_file
from machines.models import Machine, MachineProfile, Place, SystemType
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class DialectTerminalTests(TerminalClient, TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.user = get_user_model().objects.create_user("ivan", password="pw")
        self.client.force_login(self.user)

    def machine(self, style, home, files):
        system = SystemType.objects.create(code=style.upper(), name=style, path_style=style)
        main = Machine.objects.create(name="Main", hostname="aether-main", system=system.code)
        MachineProfile.objects.create(machine=main, user=self.user, name="Ivan", login="ivan", freq=1)
        Place.objects.create(system_type=system, name="home", path=home)
        for path in files:
            make_file(main, path, body="x")
        make_app(main, label="console", icon="terminal", path="/apps/terminal/")
        self.client.get(reverse("terminal:index"))                 # новое окно терминала начинает с домашней папки
        return main

    def test_vms_paths_in_and_out(self):
        self.machine("vms", "/DSK0:/OPS/ivan", ["/DSK0:/OPS/ivan/Desk/console.app", "/DSK0:/OPS/ivan/note.txt", "/DSK0:/LOGBOOK/access.lg"])
        self.assertEqual(self.run_command("pwd")["output"], "DSK0:[OPS.IVAN]")
        listing = self.run_command("ls")["output"].split()
        self.assertEqual(listing, ["DESK.DIR;1", "NOTE.TXT;1"])
        moved = self.run_command("cd [.DESK]")
        self.assertEqual((moved["exit_code"], moved["cwd"]), (0, "/DSK0:/OPS/ivan/Desk"))           # регистр не важен
        self.assertEqual(moved["shell_prompt"], "AETHER-MAIN::DSK0:[OPS.IVAN.DESK] $")
        self.assertEqual(self.run_command("ls DSK0:[LOGBOOK]")["output"], "ACCESS.LG;1")
        self.run_command("cd [-]")
        self.assertEqual(self.run_command("pwd")["output"], "DSK0:[OPS.IVAN]")
        self.assertEqual(self.run_command("cnt note.txt;1")["exit_code"], 0)
        bad = self.run_command("ls DSK0:[OPS")
        self.assertEqual(bad["exit_code"], 2)
        self.assertIn("bad file specification", bad["output"])

    def test_mainframe_data_set_names(self):
        self.machine("mvs", "/OPS/IVAN", ["/OPS/IVAN/DESK/CONSOLE", "/SYS1/PARMLIB/IEASYS00"])
        self.assertEqual(self.run_command("pwd")["output"], "OPS.IVAN")
        self.assertEqual(self.run_command("ls")["output"], "DESK")
        self.assertEqual(self.run_command("ls 'SYS1.PARMLIB'")["output"], "IEASYS00")
        self.assertEqual(self.run_command("cnt 'SYS1.PARMLIB(IEASYS00)'")["exit_code"], 0)
        moved = self.run_command("cd desk")
        self.assertEqual((moved["cwd"], moved["shell_prompt"]), ("/OPS/IVAN/DESK", "OPS.IVAN.DESK READY"))
        self.assertIn("invalid data set name", self.run_command("ls '1BAD'")["output"])

    def test_windows_drives_and_backslashes(self):
        self.machine("windows", "/C:/Users/ivan", ["/C:/Users/ivan/Desktop/a.txt", "/C:/Windows/system.ini"])
        self.assertEqual(self.run_command("pwd")["output"], "C:\\Users\\ivan")
        moved = self.run_command("cd desktop")
        self.assertEqual((moved["cwd"], moved["shell_prompt"]), ("/C:/Users/ivan/Desktop", "C:\\Users\\ivan\\Desktop>"))
        self.assertEqual(self.run_command("ls \\Windows")["output"], "system.ini")
        self.assertEqual(self.run_command("ls ..\\..\\..\\..")["exit_code"], 0)          # выше диска не уйти

    def test_the_page_starts_with_the_dialect_prompt(self):
        self.machine("vms", "/DSK0:/OPS/ivan", ["/DSK0:/OPS/ivan/note.txt"])
        html = self.client.get(reverse("terminal:index")).content.decode()
        self.assertIn("AETHER-MAIN::DSK0:[OPS.IVAN] $", html)
