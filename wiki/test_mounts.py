"""Монтирование томов: машина видит в вики только свои тома.

Запуск: python manage.py test wiki.test_mounts
"""

import json

from django.test import TestCase

from machines.models import Machine, VolumeMount
from wiki import views
from wiki.models import Document, Namespace
from wiki.test_views import call


class VolumeMountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="null", hostname="aether-null")
        cls.public = Namespace.objects.create(name="Общий")
        cls.inner = Namespace.objects.create(name="Внутренний")
        cls.sub = Namespace.objects.create(name="Подраздел", parent=cls.inner)
        Document.objects.create(namespace=cls.public, title="Общая запись", body="общее")
        Document.objects.create(namespace=cls.inner, title="Внутренняя запись", body="внутреннее", direct_link="inner-link")
        Document.objects.create(namespace=cls.sub, title="Глубокая запись", body="внутреннее")
        Document.objects.create(namespace=None, title="Корневая запись", body="общее внутреннее")

    def visit(self, fn, *args, **kwargs):
        return call(fn, *args, session={"guest": True}, **kwargs)

    def mount(self, *namespaces):
        for order, ns in enumerate(namespaces):
            VolumeMount.objects.create(machine=self.machine, namespace=ns, order=order)

    def test_without_mounts_everything_is_visible(self):
        _, html, _ = self.visit(views.resolve, "")
        self.assertIn("Общий", html)
        self.assertIn("Внутренний", html)

    def test_unmounted_volume_is_absent_from_tree_and_listing(self):
        self.mount(self.public)
        status, html, _ = self.visit(views.resolve, "")
        self.assertEqual(status, 200)
        self.assertIn("Общий", html)
        self.assertNotIn("Внутренний", html)
        self.assertIn("Корневая запись", html)  # записи вне томов не зависят от монтирования

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

    def test_only_root_namespace_can_be_mounted(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            VolumeMount(machine=self.machine, namespace=self.sub).clean()
