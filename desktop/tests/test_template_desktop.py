"""Приложения по умолчанию: файлы в шаблонной папке /home/{login}/Desktop есть на столе у каждой учётки, в том числе новой."""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem import appfile
from filesystem.models import Placement
from filesystem.testing import make_file, remove_apps
from machines.models import Machine, Place


@override_settings(FORCE_SCRIPT_NAME=None)
class TemplateDesktopTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        remove_apps()
        Place.objects.filter(name="desktop").delete()                     # место desktop по умолчанию: {home}/Desktop
        self.app("/home/{login}/Desktop/console.app", "console")
        self.app("/home/{login}/Desktop/mail.app", "intercom")

    def app(self, path, label):
        make_file(self.main, path, body=appfile.render(label, "terminal", "/apps/terminal/", "", 0, ()), format="app")

    def labels(self, login):
        user = get_user_model().objects.get_or_create(username=login)[0]
        self.client.force_login(user)
        return sorted(re.findall(r'class="icon-label">([^<]*)<', self.client.get(reverse("desktop")).content.decode()))

    def test_new_players_get_the_default_apps_without_copies(self):
        before = Placement.objects.count()
        self.assertEqual(self.labels("ivan"), ["console", "intercom"])
        self.assertEqual(self.labels("olga"), ["console", "intercom"])
        self.assertEqual(Placement.objects.count(), before)

    def test_a_personal_file_with_the_same_name_wins(self):
        self.app("/home/ivan/Desktop/mail.app", "my-mail")
        self.assertEqual(self.labels("ivan"), ["console", "my-mail"])
        self.assertEqual(self.labels("olga"), ["console", "intercom"])
