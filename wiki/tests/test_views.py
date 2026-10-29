"""Вьюхи вики с базой: доступ по пути и прямой ссылке, поиск, число запросов.

Запуск: python manage.py test wiki
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.http import Http404
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from filesystem.testing import key_item
from filesystem.testing import give_keys
from wiki import views
from wiki.testing import make_document, make_namespace

rf = RequestFactory()


def call(fn, *args, user=None, params=None, session=None):
    """(status, content, число SQL-запросов)."""
    request = rf.get("/", params or {})
    request.user = user or AnonymousUser()
    if session is not None:
        request.session = session
    with CaptureQueriesContext(connection) as ctx:
        try:
            response = fn(request, *args)
            return response.status_code, response.content.decode(), len(ctx)
        except Http404:
            return 404, "", len(ctx)


class WikiViewsTests(TestCase):
    def setUp(self):
        cache.clear()      # кэш пережил бы откат базы между тестами

    @classmethod
    def setUpTestData(cls):
        cls.root = make_namespace(name="Общий")
        cls.closed_ns = make_namespace(name="Закрытый", access="key_a")
        cls.child = make_namespace(name="Дочерний", parent=cls.closed_ns)
        cls.deep = make_namespace(name="Глубокий", parent=cls.child)
        cls.closed_doc = make_document(
            namespace=cls.closed_ns, title="Секретная", body="секретный текст",
            direct_link="closed-link",
        )
        cls.open_doc = make_document(
            namespace=cls.root, title="Открытая", body="общий текст"
        )
        cls.hidden = make_document(
            namespace=cls.root, title="Скрытая", hidden=True,
            body="тайна", direct_link="hidden-link",
        )
        cls.deep_doc = make_document(
            namespace=cls.deep, title="Вложенная", body="глубоко"
        )
        cls.key = key_item("spoiler_key")
        cls.player = get_user_model().objects.create_user("player")
        cls.held = give_keys(cls.player, cls.key.slug)
        cls.spoiler_doc = make_document(
            namespace=cls.root, title="Со спойлером",
            body="открытая часть\n\n::spoiler spoiler_key\nтайный текст\n::",
        )

    # ---------- доступ ----------

    def test_home_lists_visible_documents_only(self):
        status, html, _ = call(views.resolve, "Общий")
        self.assertEqual(status, 200)
        self.assertIn("Закрытый", html)
        self.assertIn("Открытая", html)
        self.assertNotIn("Скрытая", html)

    # ---------- вид обозревателя ----------

    def test_explorer_has_clickable_path(self):
        status, html, _ = call(views.resolve, "Закрытый/Дочерний", user=self.player, session=self.held)
        self.assertEqual(status, 403)  # у игрока нет ключа: путь всё равно виден, замка достаточно
        self.assertIn('class="crumbs"', html)
        self.assertNotIn("crumb-up", html)  # «вверх» это ссылки пути, отдельной кнопки нет

    def test_root_lists_the_buckets(self):
        status, html, _ = call(views.resolve, "")
        self.assertEqual(status, 200)
        self.assertIn("Buckets (2)", html)           # «Закрытый» (виден, но закрыт замком) и «Общий»
        self.assertIn('data-class="Bucket"', html)

    def test_the_tree_shows_icons_and_object_counts(self):
        _, html, _ = call(views.resolve, "")
        self.assertIn('class="side-head', html)
        self.assertIn("ico-bucket", html)
        self.assertIn('class="t-count">locked</span>', html)     # закрытое ведро: пометка вместо числа

    def test_object_metadata_ignores_hidden_spoilers(self):
        """Размер и etag считаются по видимому тексту: из них нельзя вытянуть закрытую часть."""
        _, anon, _ = call(views.resolve, "Общий")
        _, keyed, _ = call(views.resolve, "Общий", user=self.player, session=self.held)
        self.assertIn("data-size=", anon)
        self.assertNotEqual(
            [line for line in anon.splitlines() if "Со спойлером" in line and "data-etag" in line],
            [line for line in keyed.splitlines() if "Со спойлером" in line and "data-etag" in line],
        )

    def test_preview_skips_the_repeated_title(self):
        make_document(
            namespace=self.root, title="Статья", body="# Статья\n\nПервая фраза. Вторая фраза.\n\nАбзац."
        )
        _, html, _ = call(views.resolve, "Общий")
        self.assertIn('data-excerpt="Первая фраза. Вторая фраза.\nАбзац."', html)

    def test_locked_article_shows_no_text(self):
        make_document(namespace=self.root, title="Закрыта", body="тайный текст", access="key_a")
        _, html, _ = call(views.resolve, "Общий")
        self.assertNotIn("тайный текст", html)
        line = next(l for l in html.splitlines() if 'data-title="Закрыта"' in l)
        self.assertIn('data-excerpt=""', line)
        self.assertIn('data-modified="-"', line)     # дата тоже не раскрывается
        self.assertIn('data-storage="-"', line)

    def test_locked_article_keeps_extension(self):
        make_document(namespace=self.root, title="Закрыта", body="x", access="key_a")
        _, html, _ = call(views.resolve, "Общий")
        line = next(l for l in html.splitlines() if 'data-title="Закрыта"' in l)
        self.assertIn('data-key="Общий/Закрыта.doc"', line)
        self.assertIn('<span class="ext">.doc</span>', html)

    def test_bucket_count_includes_only_visible_articles(self):
        _, html, _ = call(views.resolve, "")
        line = next(l for l in html.splitlines() if 'data-class="Bucket"' in l and 'data-key="Закрытый/"' in l)
        self.assertIn('data-objects="2"', line)  # «Секретная» и «Вложенная»
        self.assertNotIn("Скрытая", html)

    def test_bucket_count_follows_new_and_removed_articles_despite_the_cache(self):
        def objects():
            _, html, _ = call(views.resolve, "")
            return next(l for l in html.splitlines() if 'data-class="Bucket"' in l and 'data-key="Общий/"' in l)

        self.assertIn('data-objects="2"', objects())             # «Открытая» и «Со спойлером»; «Скрытая» не видна
        self.assertIn('data-objects="2"', objects())           # из кэша
        added = make_document(namespace=self.root, title="Ещё одна", body="x")
        self.assertIn('data-objects="3"', objects())
        added.placement.delete()
        self.assertIn('data-objects="2"', objects())

    def test_cached_rows_follow_an_edited_article(self):
        _, html, _ = call(views.resolve, "Общий")
        self.assertIn("Открытая", html)
        call(views.resolve, "Общий")                                  # из кэша
        pass
        from filesystem.models import Item

        Item.objects.filter(pk=self.open_doc.item.pk).update(name="Переименована")
        from wiki.versioning import bump_version

        bump_version()
        _, html, _ = call(views.resolve, "Общий")
        self.assertIn("Переименована", html)
        self.assertNotIn(">Открытая<", html)

    def test_objects_have_s3_style_keys_and_uris(self):
        _, html, _ = call(views.resolve, "Общий")
        self.assertIn('data-key="Общий/Открытая.doc"', html)
        self.assertIn('data-uri="aether://Общий/Открытая.doc"', html)
        bucket = make_namespace(name="Корень")
        make_document(namespace=bucket, title="Лист", body="текст")
        _, html, _ = call(views.resolve, "Корень")
        self.assertIn('data-uri="aether://Корень/Лист.doc"', html)

    def test_last_modified_is_the_world_date_or_the_real_time(self):
        import datetime

        make_document(namespace=self.root, title="Датированная", body="х", world_date=datetime.date(2027, 10, 3))
        _, html, _ = call(views.resolve, "Общий")
        line = next(l for l in html.splitlines() if 'data-title="Датированная"' in l)
        self.assertIn('data-modified="Oct 3, 2027"', line)
        other = next(l for l in html.splitlines() if 'data-title="Открытая"' in l)
        self.assertNotIn("2027", other)               # без даты в мире показывается реальное время

    def test_locked_object_has_no_size_or_etag(self):
        locked = make_document(namespace=self.root, title="Замок", body="х" * 50, access="key_a")
        _, html, _ = call(views.resolve, "Общий")
        line = next(l for l in html.splitlines() if 'data-title="Замок"' in l)
        self.assertIn('data-size="-"', line)
        self.assertIn('data-etag="-"', line)
        self.assertNotIn("50", line.split("data-size")[1][:8])
        locked.placement.delete()

    def test_locked_section_shows_no_rows(self):
        status, html, _ = call(views.resolve, "Закрытый")
        self.assertEqual(status, 403)
        self.assertNotIn('id="docs"', html)
        self.assertNotIn("Вложенная", html)

    def test_closed_section_is_not_expanded_into_rows(self):
        """Строки подразделов берутся из дерева: за замок они не заглядывают."""
        _, html, _ = call(views.resolve, "")
        self.assertIn("Закрытый", html)
        self.assertNotIn("Дочерний", html)

    def test_closed_namespace_is_locked(self):
        status, html, _ = call(views.resolve, "Закрытый")
        self.assertEqual(status, 403)
        self.assertNotIn("Секретная", html)

    def test_document_in_closed_namespace_is_locked(self):
        status, html, _ = call(views.resolve, "Закрытый/Секретная")
        self.assertEqual(status, 403)
        self.assertNotIn("секретный текст", html)

    def test_open_document(self):
        status, html, _ = call(views.resolve, "Общий/Открытая")
        self.assertEqual(status, 200)
        self.assertIn("общий текст", html)

    def test_hidden_document_is_404_by_path_but_open_by_direct_link(self):
        self.assertEqual(call(views.resolve, "Общий/Скрытая")[0], 404)
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
        _, guest, _ = call(views.resolve, "Общий/Со спойлером")
        _, player, _ = call(views.resolve, "Общий/Со спойлером", user=self.player, session=self.held)
        self.assertNotIn("тайный текст", guest)
        self.assertIn("тайный текст", player)

    def test_search_respects_spoilers(self):
        _, body, _ = call(views.search, params={"q": "тайный"})
        self.assertEqual(json.loads(body)["rows"], [])
        _, body, _ = call(views.search, params={"q": "тайный"}, user=self.player, session=self.held)
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
            "document": call(views.resolve, "Общий/Открытая")[2],
            "deep_document": call(views.resolve, "Закрытый/Дочерний/Глубокий/Вложенная")[2],
            "direct": call(views.direct, "hidden-link")[2],
            "search": call(views.search, params={"q": "текст"})[2],
        }
        # потолки с запасом; главное - не растут с глубиной пути
        for name, limit in {
            "home": 5,
            "namespace": 5,
            "document": 5,
            "deep_document": 5,
            "direct": 5,
            "search": 5,
        }.items():
            self.assertLessEqual(counts[name], limit, f"{name}: {counts[name]} запросов")


class ViewAsTests(TestCase):
    def setUp(self):
        cache.clear()      # кэш пережил бы откат базы между тестами

    """Подмена ключей сотрудником (?as=...), запоминается в сессии."""

    LOCKED = "ACCESS DENIED"

    @classmethod
    def setUpTestData(cls):
        locked = make_namespace(name="Закрытый", access="key_a")
        make_document(locked, "Страница")
        key_item("key_a")
        User = get_user_model()
        cls.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        cls.player = User.objects.create_user("player", password="pw")

    def page(self, user, session, params=None):
        return call(views.resolve, "Закрытый", user=user, params=params, session=session)[1]

    def test_staff_without_override_sees_player_view(self):
        self.assertIn(self.LOCKED, self.page(self.staff, {}))

    def test_staff_can_open_as_player_with_all_keys(self):
        html = self.page(self.staff, {}, {"as": "all"})
        self.assertNotIn(self.LOCKED, html)
        self.assertIn("со всеми ключами", html)

    def test_override_sticks_until_reset(self):
        session = {}
        self.page(self.staff, session, {"as": "key_a"})
        self.assertNotIn(self.LOCKED, self.page(self.staff, session))
        self.page(self.staff, session, {"as": "reset"})
        self.assertIn(self.LOCKED, self.page(self.staff, session))

    def test_none_hides_what_all_would_open(self):
        session = {}
        self.page(self.staff, session, {"as": "all"})
        self.assertIn(self.LOCKED, self.page(self.staff, session, {"as": "none"}))

    def test_document_page_shows_the_banner_too(self):
        make_document(make_namespace(name="Корень"), title="Открытая", body="текст")
        html = call(views.resolve, "Корень/Открытая", user=self.staff, params={"as": "none"}, session={})[1]
        self.assertIn("Просмотр как игрок", html)
        self.assertIn("без ключей", html)

    def test_ordinary_player_cannot_use_it(self):
        html = self.page(self.player, {}, {"as": "all"})
        self.assertIn(self.LOCKED, html)
        self.assertNotIn("Просмотр как игрок", html)
