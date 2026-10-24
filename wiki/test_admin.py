"""Списки админки: фильтры, поиск, действия, ключи.

Запуск: python manage.py test wiki.test_admin
"""

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import get_script_prefix, reverse, set_script_prefix

from secure.models import Key
from users.models import UserKey
from wiki.key_usage import key_usage
from wiki.models import Document, Namespace


@override_settings(FORCE_SCRIPT_NAME=None)
class AdminTestCase(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.admin = get_user_model().objects.create_superuser("root", password="pw")
        self.client.force_login(self.admin)


class DocumentListTests(AdminTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tech = Namespace.objects.create(name="Тех")
        cls.guns = Namespace.objects.create(name="Оружие", parent=cls.tech)
        cls.other = Namespace.objects.create(name="Прочее")
        cls.rifle = Document.objects.create(namespace=cls.guns, title="Винтовка", body="найди секрет")
        cls.lore = Document.objects.create(namespace=cls.other, title="Лор", access="key_a")
        cls.root_doc = Document.objects.create(title="Корень")

    def titles(self, params=None):
        response = self.client.get(reverse("admin:wiki_document_changelist"), params or {})
        self.assertEqual(response.status_code, 200)
        return sorted(d.title for d in response.context["cl"].result_list)

    def test_search_covers_body(self):
        self.assertEqual(self.titles({"q": "секрет"}), ["Винтовка"])

    def test_namespace_filter_includes_nested_sections(self):
        self.assertEqual(self.titles({"ns": self.tech.pk}), ["Винтовка"])
        self.assertEqual(self.titles({"ns": "root"}), ["Корень"])

    def test_protection_filter(self):
        self.assertEqual(self.titles({"protection": "access"}), ["Лор"])
        self.assertEqual(self.titles({"protection": "open"}), ["Винтовка", "Корень"])

    def test_query_count_does_not_grow_with_rows(self):
        url = reverse("admin:wiki_document_changelist")
        with CaptureQueriesContext(connection) as before:
            self.client.get(url)
        for i in range(10):
            Document.objects.create(namespace=self.guns, title=f"Новая {i}")
        with CaptureQueriesContext(connection) as after:
            self.client.get(url)
        self.assertEqual(len(before), len(after))

    def test_player_links_in_list_and_change_form(self):
        list_page = self.client.get(reverse("admin:wiki_document_changelist"))
        self.assertContains(list_page, "?as=none")
        form = self.client.get(reverse("admin:wiki_document_change", args=[self.rifle.pk]))
        self.assertContains(form, "?as=all")


class MoveActionTests(AdminTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.src = Namespace.objects.create(name="Откуда")
        cls.dst = Namespace.objects.create(name="Куда")
        cls.a = Document.objects.create(namespace=cls.src, title="А")
        cls.b = Document.objects.create(namespace=cls.src, title="Б")
        Document.objects.create(namespace=cls.dst, title="Б")  # занято

    def run_action(self, **extra):
        data = {
            "action": "move_to_namespace",
            ACTION_CHECKBOX_NAME: [self.a.pk, self.b.pk],
            **extra,
        }
        return self.client.post(reverse("admin:wiki_document_changelist"), data, follow=True)

    def test_form_is_shown_first(self):
        response = self.run_action()
        self.assertContains(response, "Новый раздел")
        self.a.refresh_from_db()
        self.assertEqual(self.a.namespace, self.src)

    def test_moves_what_it_can_and_reports_the_rest(self):
        response = self.run_action(apply="1", namespace=self.dst.pk)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.namespace, self.dst)
        self.assertEqual(self.b.namespace, self.src)
        text = "".join(str(m) for m in response.context["messages"])
        self.assertIn("Перемещено записей: 1", text)
        self.assertIn("Не перемещена «Б»", text)

    def test_move_to_root(self):
        self.run_action(apply="1", namespace="")
        self.a.refresh_from_db()
        self.assertIsNone(self.a.namespace)


class NamespaceListTests(AdminTestCase):
    def test_counts(self):
        parent = Namespace.objects.create(name="П")
        Namespace.objects.create(name="Д", parent=parent)
        Document.objects.create(namespace=parent, title="X")
        Document.objects.create(namespace=parent, title="Y")
        response = self.client.get(reverse("admin:wiki_namespace_changelist"))
        row = next(n for n in response.context["cl"].result_list if n.pk == parent.pk)
        self.assertEqual((row._documents, row._children), (2, 1))


class KeyAdminTests(AdminTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.key = Key.objects.create(slug="key_a")
        Key.objects.create(slug="key_ab")
        cls.player = get_user_model().objects.create_user("player", password="pw")
        ns = Namespace.objects.create(name="Закрытый", access="key_a")
        cls.doc = Document.objects.create(namespace=ns, title="Д", body="[x]{key_a}")
        cls.decoy = Document.objects.create(title="Двойник", body="[x]{key_ab}")

    def test_usage_finds_exact_slug_only(self):
        documents, namespaces = key_usage("key_a")
        self.assertEqual([d.title for d in documents], ["Д"])
        self.assertEqual([n.name for n in namespaces], ["Закрытый"])

    def test_change_page_lists_usage(self):
        response = self.client.get(reverse("admin:secure_key_change", args=[self.key.pk]))
        self.assertContains(response, "запись: <a")
        self.assertContains(response, "Закрытый:Д</a>")
        self.assertNotContains(response, "Двойник")

    def test_grant_and_revoke(self):
        url = reverse("admin:secure_key_changelist")
        base = {"action": "grant", ACTION_CHECKBOX_NAME: [self.key.pk]}
        self.client.post(url, {**base, "apply": "1", "users": [self.player.pk]})
        self.assertTrue(UserKey.objects.filter(user=self.player, key=self.key).exists())

        self.client.post(url, {**base, "apply": "1", "users": [self.player.pk]})  # повтор безвреден
        self.assertEqual(UserKey.objects.filter(user=self.player, key=self.key).count(), 1)

        base["action"] = "revoke"
        self.client.post(url, {**base, "apply": "1", "users": [self.player.pk]})
        self.assertFalse(UserKey.objects.filter(user=self.player).exists())

    def test_list_shows_holders(self):
        UserKey.objects.create(user=self.player, key=self.key)
        response = self.client.get(reverse("admin:secure_key_changelist"))
        holders = {k.slug: k._holders for k in response.context["cl"].result_list}
        self.assertEqual(holders, {"key_a": 1, "key_ab": 0})


class NamespaceConditionTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        Key.objects.create(slug="key_a", description="первый")
        self.ns = Namespace.objects.create(name="Раздел")

    def data(self, **extra):
        return {"name": "Раздел", "slug": "", "parent": "", "visibility": "{}", "access": "{}", **extra}

    def url(self):
        return reverse("admin:wiki_namespace_change", args=[self.ns.pk])

    def test_page_uses_the_visual_condition_editor(self):
        response = self.client.get(self.url())
        self.assertContains(response, "data-condition-editor")
        self.assertContains(response, "condition_editor.js")
        self.assertContains(response, "key_a")  # список ключей для редактора

    def test_valid_condition_is_saved(self):
        self.client.post(self.url(), self.data(access='{"all": ["key_a", "key_b"]}'))
        self.ns.refresh_from_db()
        self.assertEqual(self.ns.access, {"all": ["key_a", "key_b"]})

    def test_invalid_condition_is_rejected(self):
        response = self.client.post(self.url(), self.data(access='{"xor": ["key_a"]}'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неверное условие")
        self.ns.refresh_from_db()
        self.assertEqual(self.ns.access, {})

    def test_blank_condition_is_saved_as_an_empty_object_not_none(self):
        # access/visibility не допускают NULL: пустое значение не должно ронять сохранение
        response = self.client.post(self.url(), self.data(access="", visibility=""))
        self.assertEqual(response.status_code, 302)
        self.ns.refresh_from_db()
        self.assertEqual((self.ns.access, self.ns.visibility), ({}, {}))

    def test_list_shows_the_condition_as_text(self):
        Namespace.objects.filter(pk=self.ns.pk).update(access={"all": ["a", {"any": ["b", "c"]}]})
        response = self.client.get(reverse("admin:wiki_namespace_changelist"))
        self.assertContains(response, "закрыта: a and (b or c)")
