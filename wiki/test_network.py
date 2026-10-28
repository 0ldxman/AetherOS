"""Вики подключается к хостам: строка volume файла вики называет хост, путь на нём и запись хоста.

Запуск: python manage.py test wiki.test_network
"""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from filesystem.models import Placement
from filesystem.testing import make_app
from machines.current import SESSION_KEY
from machines.models import Export, Machine, MachineMount, MachineProfile, Session
from wiki import views
from wiki.test_views import call
from wiki.testing import make_document, make_namespace


class WikiNetworkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.client_machine = Machine.objects.create(name="Main", hostname="aether-main")
        profile = MachineProfile.objects.create(machine=cls.client_machine, user=cls.user, name="Ivan", login="ivan", freq=1)
        cls.session = {SESSION_KEY: Session.objects.create(user=cls.user, profile=profile).pk}
        cls.host = Machine.objects.create(name="Archive", hostname="archive-srv")
        MachineProfile.objects.create(machine=cls.host, login="reader", name="Reader", freq=1)
        cls.archive = make_namespace("Архив порта")
        cls.page = make_document(cls.archive, "Манифест", body="груз")
        cls.closed = make_document(cls.archive, "Закрытая", body="тайна")
        Placement.objects.filter(pk=cls.closed.placement.pk).update(owner="root", mode="600")
        MachineMount.objects.create(machine=cls.host, volume=cls.archive.volume, mount_path="/srv/harbor")
        Export.objects.create(machine=cls.host, path="/srv/harbor")

    def setUp(self):
        cache.clear()

    def wiki(self, *lines):
        make_app(self.client_machine, "wiki", "W", "/apps/wiki/", volumes=lines)

    def get(self, fn, *args, **kwargs):
        return call(fn, *args, user=self.user, session=self.session, **kwargs)

    def test_without_a_wiki_file_the_machine_has_no_sections(self):
        _, html, _ = self.get(views.resolve, "")
        self.assertNotIn("Манифест", html)
        self.assertNotIn("Архив", html)

    def test_a_section_is_a_path_on_a_host_seen_by_the_account_and_a_closed_page_is_not_listed(self):
        self.wiki("archive-srv:/srv/harbor as Harbor user=reader")
        status, html, _ = self.get(views.resolve, "Harbor")
        self.assertEqual(status, 200)
        self.assertIn("Манифест", html)
        self.assertNotIn("Закрытая", html)                                      # reader не читает файл 600 root
        self.assertEqual(self.get(views.resolve, "Harbor/Манифест")[0], 200)
        self.assertEqual(self.get(views.direct, self.page.direct_link)[0], 200)
        self.assertEqual(self.get(views.direct, self.closed.direct_link)[0], 404)

    def test_the_title_defaults_to_the_folder_name_and_the_search_finds_the_pages(self):
        self.wiki("archive-srv:/srv/harbor user=reader")
        _, body, _ = self.get(views.search, params={"q": "груз"})
        self.assertEqual([row["title"] for row in json.loads(body)["rows"]], ["Манифест"])
        self.assertEqual(self.get(views.resolve, "harbor")[0], 200)

    def test_a_path_the_host_does_not_export_or_a_wrong_account_gives_no_section(self):
        self.wiki("archive-srv:/srv as Wide user=reader", "archive-srv:/srv/harbor as Nobody user=stranger")
        self.assertEqual(self.get(views.resolve, "Wide")[0], 404)
        self.assertEqual(self.get(views.resolve, "Nobody")[0], 404)

    def test_the_path_of_the_own_machine_needs_no_host(self):
        MachineMount.objects.create(machine=self.client_machine, volume=self.archive.volume, mount_path="/wiki/local")
        self.wiki("/wiki/local as Local")
        self.assertEqual(self.get(views.resolve, "Local/Манифест")[0], 200)

    def test_the_file_of_the_wiki_is_validated(self):
        from django.core.exceptions import ValidationError

        from filesystem import appfile

        with self.assertRaises(ValidationError):
            appfile.parse("label w\nglyph W\npath /apps/wiki/\nvolume not a line")
