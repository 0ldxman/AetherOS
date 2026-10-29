"""Окно документа: cnt на файле формата с разметкой открывает /view/doc/, документ разобран парсером и в стилях своего типа.

Запуск: python manage.py test documents.tests.test_window
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.testing import make_app, make_file
from machines.models import Machine, MachineProfile
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class DocumentWindowTests(TerminalClient, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1, mail="ivan@aether-main")
        make_file(cls.main, "/home/report.rec", body="Отчёт.\n\n::spoiler door_key\nкод двери\n::", format="rec")
        make_file(cls.main, "/home/notes.txt", body="просто текст", format="txt")
        sealed = make_file(cls.main, "/home/sealed.doc", body="закрыто", format="doc").item
        sealed.access = {"all": ["door_key"]}
        sealed.save()

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def window(self, path):
        data = self.run_command(f"cnt {path}")
        self.assertEqual(data["exit_code"], 0, data)
        return data["window"]["url"]

    def test_cnt_opens_the_document_window_with_its_type(self):
        url = self.window("/home/report.rec")
        self.assertTrue(url.startswith("/view/doc/?path="), url)
        html = self.client.get(url).content.decode()
        self.assertIn("doc--rec", html)
        self.assertIn("document/rec.css", html)
        self.assertIn("Отчёт.", html)
        self.assertNotIn("::spoiler", html)                # разобрано парсером, а не показано текстом
        self.assertNotIn("код двери", html)                # спойлер без ключа закрыт

    def test_a_file_without_markup_opens_as_text(self):
        url = self.window("/home/notes.txt")
        self.assertTrue(url.startswith("/view/fs/text/?path="), url)
        self.assertEqual(self.client.get("/view/doc/?path=/home/notes.txt").status_code, 404)

    def test_a_file_closed_by_a_key_shows_the_lock(self):
        html = self.client.get("/view/doc/?path=/home/sealed.doc").content.decode()
        self.assertIn("Доступ закрыт", html)
        self.assertNotIn("закрыто", html.replace("Доступ закрыт", ""))

    def test_a_missing_or_foreign_address_is_404(self):
        self.assertEqual(self.client.get("/view/doc/?path=/home/none.rec").status_code, 404)
        self.assertEqual(self.client.get("/view/doc/").status_code, 404)
        self.assertEqual(self.client.get("/view/doc/?wiki=12").status_code, 404)          # неподписанный id раздела
