"""Вьюхи вики с базой: доступ по пути и прямой ссылке, поиск, число запросов.

Запуск: python manage.py test wiki
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from secure.models import Key
from users.models import UserKey
from wiki import views
from wiki.models import Document, Namespace

rf = RequestFactory()


def call(fn, *args, user=None, params=None):
    """(status, content, число SQL-запросов)."""
    request = rf.get("/", params or {})
    request.user = user or AnonymousUser()
    with CaptureQueriesContext(connection) as ctx:
        try:
            response = fn(request, *args)
            return response.status_code, response.content.decode(), len(ctx)
        except Http404:
            return 404, "", len(ctx)


class WikiViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.closed_ns = Namespace.objects.create(name="Закрытый", access="key_a")
        cls.child = Namespace.objects.create(name="Дочерний", parent=cls.closed_ns)
        cls.deep = Namespace.objects.create(name="Глубокий", parent=cls.child)
        cls.closed_doc = Document.objects.create(
            namespace=cls.closed_ns, title="Секретная", body="секретный текст",
            direct_link="closed-link",
        )
        cls.open_doc = Document.objects.create(
            namespace=None, title="Открытая", body="общий текст"
        )
        cls.hidden = Document.objects.create(
            namespace=None, title="Скрытая", visibility="key_b",
            body="тайна", direct_link="hidden-link",
        )
        cls.deep_doc = Document.objects.create(
            namespace=cls.deep, title="Вложенная", body="глубоко"
        )
        cls.key = Key.objects.create(slug="spoiler_key")
        cls.player = get_user_model().objects.create_user("player")
        UserKey.objects.create(user=cls.player, key=cls.key)
        cls.spoiler_doc = Document.objects.create(
            namespace=None, title="Со спойлером",
            body="открытая часть\n\n::spoiler spoiler_key\nтайный текст\n::",
        )

    # ---------- доступ ----------

    def test_home_lists_visible_documents_only(self):
        status, html, _ = call(views.resolve, "")
        self.assertEqual(status, 200)
        self.assertIn("Закрытый", html)
        self.assertIn("Открытая", html)
        self.assertNotIn("Скрытая", html)

    def test_closed_namespace_is_locked(self):
        status, html, _ = call(views.resolve, "Закрытый")
        self.assertEqual(status, 403)
        self.assertNotIn("Секретная", html)

    def test_document_in_closed_namespace_is_locked(self):
        status, html, _ = call(views.resolve, "Закрытый/Секретная")
        self.assertEqual(status, 403)
        self.assertNotIn("секретный текст", html)

    def test_open_document(self):
        status, html, _ = call(views.resolve, "Открытая")
        self.assertEqual(status, 200)
        self.assertIn("общий текст", html)

    def test_hidden_document_is_404_by_path_but_open_by_direct_link(self):
        self.assertEqual(call(views.resolve, "Скрытая")[0], 404)
        status, html, _ = call(views.direct, "hidden-link")
        self.assertEqual(status, 200)
        self.assertIn("тайна", html)

    def test_closed_document_by_direct_link_hides_title(self):
        status, html, _ = call(views.direct, "closed-link")
        self.assertEqual(status, 403)
        self.assertNotIn("Секретная", html)

    def test_unknown_paths_are_404(self):
        self.assertEqual(call(views.direct, "нет")[0], 404)
        self.assertEqual(call(views.resolve, "Нет/Открытая")[0], 404)
        self.assertEqual(call(views.resolve, "Закрытый/Нет")[0], 404)

    def test_nested_document_inherits_lock(self):
        status, _, _ = call(views.resolve, "Закрытый/Дочерний/Глубокий/Вложенная")
        self.assertEqual(status, 403)

    # ---------- спойлеры и поиск ----------

    def test_spoiler_open_only_with_key(self):
        _, guest, _ = call(views.resolve, "Со спойлером")
        _, player, _ = call(views.resolve, "Со спойлером", user=self.player)
        self.assertNotIn("тайный текст", guest)
        self.assertIn("тайный текст", player)

    def test_search_respects_spoilers(self):
        _, body, _ = call(views.search, params={"q": "тайный"})
        self.assertEqual(json.loads(body)["rows"], [])
        _, body, _ = call(views.search, params={"q": "тайный"}, user=self.player)
        rows = json.loads(body)["rows"]
        self.assertEqual([r["title"] for r in rows], ["Со спойлером"])

    def test_search_skips_closed_namespace(self):
        _, body, _ = call(views.search, params={"q": "секретный"})
        self.assertEqual(json.loads(body)["rows"], [])

    # ---------- число запросов ----------

    def test_query_counts(self):
        """Потолки запросов: не должны расти с глубиной дерева."""
        counts = {
            "home": call(views.resolve, "")[2],
            "namespace": call(views.resolve, "Закрытый/Дочерний/Глубокий")[2],
            "document": call(views.resolve, "Открытая")[2],
            "deep_document": call(views.resolve, "Закрытый/Дочерний/Глубокий/Вложенная")[2],
            "direct": call(views.direct, "hidden-link")[2],
            "search": call(views.search, params={"q": "текст"})[2],
        }
        # потолки с запасом; главное - не растут с глубиной пути
        for name, limit in {
            "home": 3,
            "namespace": 3,
            "document": 3,
            "deep_document": 3,
            "direct": 2,
            "search": 3,
        }.items():
            self.assertLessEqual(counts[name], limit, f"{name}: {counts[name]} запросов")
