"""Файлы приложений: иконки рабочего стола.

Запуск: python manage.py test filesystem.tests.test_appfile
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from filesystem import appfile
from filesystem.models import Item
from filesystem.testing import give_keys, key_item, make_app, make_file
from machines.current import SESSION_KEY, machine_has_app, visible_apps
from machines.models import Machine, MachineProfile, Session


class ParseTests(TestCase):
    def test_a_file_gives_its_icon(self):
        spec = appfile.parse("# окно\nlabel aether\nglyph W\nsuffix db\npath /apps/wiki/\norder 2\nunknown x\n")
        self.assertEqual((spec.label, spec.glyph, spec.suffix, spec.path, spec.order), ("aether", "W", ".db", "/apps/wiki/", 2))

    def test_a_missing_line_or_a_foreign_path_is_an_error(self):
        for text in ("glyph W\npath /apps/wiki/", "label a\nglyph W\npath https://evil.example/", "label a\nglyph W\npath /no/such/", "label a\nglyph W\npath /apps/wiki/\norder x"):
            with self.assertRaises(ValidationError, msg=text):
                appfile.parse(text)

    def test_the_object_form_checks_the_text(self):
        item = Item(slug="bad", name="bad", format="app", body="label only")
        with self.assertRaises(ValidationError):
            item.clean()


class DesktopTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, user=cls.user, name="Ivan", login="ivan", freq=1)

    def request(self):
        request = RequestFactory().get("/")
        request.user = self.user
        session = Session.objects.create(user=self.user, profile=self.profile)
        request.session = {SESSION_KEY: session.pk}
        return request

    def labels(self):
        request = self.request()
        return [app.label for app in visible_apps(request, self.machine)]

    def test_icons_follow_the_order_line_and_then_the_name(self):
        make_app(self.machine, "wiki", "W", "/apps/wiki/", order=2)
        make_app(self.machine, "console", ">_", "/apps/terminal/", order=1)
        make_app(self.machine, "world", "M", "/apps/map/", order=2)
        self.assertEqual(self.labels(), ["console", "wiki", "world"])

    def test_a_hidden_file_and_a_plain_file_are_not_icons(self):
        made = make_app(self.machine, "wiki", "W", "/apps/wiki/")
        made.placement.hidden = True
        made.placement.save()
        make_file(self.machine, "/apps-desktop/readme.txt", body="hello")
        self.assertEqual(self.labels(), [])

    def test_a_file_with_a_condition_needs_the_key(self):
        key_item("badge")
        make_app(self.machine, "wiki", "W", "/apps/wiki/", key_condition="badge")
        self.assertEqual(self.labels(), [])
        request = self.request()
        request.session = give_keys(self.user, "badge")
        self.assertEqual([app.label for app in visible_apps(request, self.machine)], ["wiki"])
        self.assertTrue(machine_has_app(request, "wiki"))

    def test_the_desktop_of_a_record_is_its_own_folder(self):
        make_file(self.machine, "/home/ivan/Desktop/wiki.app", body=appfile.render("wiki", "W", "/apps/wiki/"), format="app")
        self.assertEqual(self.labels(), ["wiki"])
