"""Сводка автора: связи между записями, неиспользуемые ассеты и ключи.

Запуск: python manage.py test wiki.test_dashboard
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from assets.models import Asset
from secure.models import Key
from wiki import dashboard
from wiki.testing import make_document, make_namespace


class DashboardDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ns = make_namespace("Тех")
        free = make_namespace("Прочее")
        cls.target = make_document(ns, "Цель", direct_link="goal")
        cls.linker = make_document(ns, "Ссылка", body="[к цели](/apps/wiki/Тех/Цель) и ещё [x]{key_used}")
        cls.by_go = make_document(free, "Через go", body="[a](/apps/wiki/go/goal/)")
        cls.lonely = make_document(free, "Одинокая")
        cls.broken = make_document(free, "Сломанная", body="::box\nнет конца\n")
        cls.selfref = make_document(free, "Сама", body="[я](/apps/wiki/Прочее/Сама)")
        make_document(free, "Закрытая", access="key_gate")

        Key.objects.create(slug="key_used")
        Key.objects.create(slug="key_gate")
        Key.objects.create(slug="key_idle")

        Asset.objects.create(name="Использован", slug="in-use", file_id="1", viewer_type=Asset.ViewerType.AUDIO)
        Asset.objects.create(name="Лишний", slug="idle", file_id="2")
        make_document(free, "С ассетом", body="::audio in-use title=Т\n")

        cls.data = dashboard.build()

    def titles(self, rows):
        return sorted(row[0].title for row in rows)

    def test_orphans_are_documents_nobody_links_to(self):
        orphans = self.titles(self.data.orphans)
        self.assertNotIn("Цель", orphans)  # на неё ссылаются и по пути, и по go
        self.assertIn("Одинокая", orphans)
        self.assertIn("Ссылка", orphans)   # сама ссылается, но на неё никто

    def test_link_to_itself_does_not_count(self):
        self.assertIn("Сама", self.titles(self.data.orphans))

    def test_broken_markup_is_listed_with_count(self):
        rows = {doc.title: count for doc, _, count in self.data.broken}
        self.assertEqual(rows, {"Сломанная": 1})

    def test_unused_assets_and_keys(self):
        self.assertEqual([a.slug for a in self.data.unused_assets], ["idle"])
        self.assertEqual([k.slug for k in self.data.unused_keys], ["key_idle"])

    def test_access_conditions_count_as_key_usage(self):
        self.assertNotIn("key_gate", [k.slug for k in self.data.unused_keys])

    def test_recent_is_newest_first_and_has_full_path(self):
        self.assertEqual(self.data.recent[0][0].title, "С ассетом")
        paths = {doc.title: path for doc, path in self.data.recent}
        self.assertEqual(paths["Цель"], "Тех:Цель")

    def test_totals(self):
        self.assertEqual(self.data.totals["documents"], 8)


@override_settings(FORCE_SCRIPT_NAME=None)
class DashboardPageTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        make_document(make_namespace("Раздел"), "Одна")
        self.client.force_login(get_user_model().objects.create_superuser("root", password="pw"))

    def test_page_renders(self):
        response = self.client.get(reverse("admin:filesystem_item_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сводка автора")
        self.assertContains(response, "Одна")

    def test_list_links_to_dashboard(self):
        response = self.client.get(reverse("admin:filesystem_item_changelist"))
        self.assertContains(response, reverse("admin:filesystem_item_dashboard"))

    def test_requires_staff(self):
        self.client.logout()
        response = self.client.get(reverse("admin:filesystem_item_dashboard"))
        self.assertEqual(response.status_code, 302)
