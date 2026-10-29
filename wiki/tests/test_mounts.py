"""Монтирование томов: машина видит в вики только свои тома.

Запуск: python manage.py test wiki.tests.test_mounts
"""

import json

from django.test import TestCase

from filesystem.models import Volume
from filesystem.testing import wiki_sections
from machines.models import Machine, MachineMount
from wiki import views
from wiki.tests.test_views import call
from wiki.testing import make_document, make_namespace


class VolumeMountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="null", hostname="aether-null")
        cls.public = make_namespace(name="Общий")
        cls.inner = make_namespace(name="Внутренний")
        cls.sub = make_namespace(name="Подраздел", parent=cls.inner)
        make_document(namespace=cls.public, title="Общая запись", body="общее")
        make_document(namespace=cls.inner, title="Внутренняя запись", body="внутреннее", direct_link="inner-link")
        make_document(namespace=cls.sub, title="Глубокая запись", body="внутреннее")
        make_document(namespace=cls.public, title="Корневая запись", body="общее внутреннее")

    def visit(self, fn, *args, **kwargs):
        return call(fn, *args, session={"guest": True}, **kwargs)

    def mount(self, *namespaces):
        wiki_sections(self.machine, [ns.volume for ns in namespaces])

    def test_without_mounts_nothing_is_visible(self):
        status, html, _ = self.visit(views.resolve, "")
        self.assertEqual(status, 200)
        self.assertNotIn("Общий", html)
        self.assertNotIn("Внутренний", html)
        self.assertEqual(self.visit(views.resolve, "Общий")[0], 404)
        self.assertEqual(self.visit(views.direct, "inner-link")[0], 404)

    def test_without_a_machine_nothing_is_filtered(self):
        _, html, _ = call(views.resolve, "")
        self.assertIn("Общий", html)
        self.assertIn("Внутренний", html)

    def test_unmounted_volume_is_absent_from_tree_and_listing(self):
        self.mount(self.public)
        status, html, _ = self.visit(views.resolve, "")
        self.assertEqual(status, 200)
        self.assertIn("Общий", html)
        self.assertNotIn("Внутренний", html)

    def test_unmounted_volume_and_its_children_are_404_by_path(self):
        self.mount(self.public)
        self.assertEqual(self.visit(views.resolve, "Внутренний")[0], 404)
        self.assertEqual(self.visit(views.resolve, "Внутренний/Подраздел")[0], 404)
        self.assertEqual(self.visit(views.resolve, "Внутренний/Внутренняя запись")[0], 404)

    def test_unmounted_document_is_not_reachable_by_direct_link(self):
        self.mount(self.public)
        self.assertEqual(self.visit(views.direct, "inner-link")[0], 404)

    def test_unmounted_documents_are_not_in_search(self):
        self.mount(self.public)
        _, body, _ = self.visit(views.search, params={"q": "внутреннее"})
        titles = [row["title"] for row in json.loads(body)["rows"]]
        self.assertEqual(titles, ["Корневая запись"])

    def test_mounted_volume_is_fully_available(self):
        self.mount(self.inner)
        self.assertEqual(self.visit(views.resolve, "Внутренний/Подраздел")[0], 200)
        self.assertEqual(self.visit(views.direct, "inner-link")[0], 200)

    def test_mount_order_sets_tree_order(self):
        self.mount(self.inner, self.public)
        _, html, _ = self.visit(views.resolve, "")
        self.assertLess(html.index("Внутренний"), html.index("Общий"))
