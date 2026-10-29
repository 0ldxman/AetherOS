"""Где используется ключ: вики, машины, файлы.

Запуск: python manage.py test secure.tests.test_usage
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import embed_key, make_file, make_app, remove_apps
from machines.models import Machine, MachineProfile
from filesystem.testing import key_item
from secure.usage import key_usage, used_slugs
from wiki import dashboard
from wiki.testing import make_document, make_namespace


class UsageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for slug in ("key_a", "key_ab", "key_idle", "key_file", "key_prof", "key_doc"):
            key_item(slug)
        machine = Machine.objects.create(name="Main", hostname="main")
        make_app(machine, "wiki", "W", "/apps/wiki/", key_condition={"all": ["key_a", {"not": "key_x"}]})
        MachineProfile.objects.create(machine=machine, name="P", login="l", freq=1, key_condition="key_prof")
        embed_key(make_file(machine, "/secret.txt").item, "key_file")
        make_document(make_namespace("Раздел"), "Док", body="[x]{key_doc}")

    def kinds(self, slug):
        return sorted((u.kind, u.label) for u in key_usage(slug))

    def test_app_condition_counts(self):
        self.assertEqual(self.kinds("key_a"), [("объект", "wiki.app [wikiapp]")])

    def test_exact_slug_not_substring(self):
        self.assertEqual(self.kinds("key_ab"), [])

    def test_profile_condition_counts(self):
        self.assertEqual(self.kinds("key_prof"), [("профиль", "l@main:1.000")])

    def test_file_key_counts(self):
        self.assertEqual(self.kinds("key_file"), [("объект", "secret.txt [secrettxt]")])

    def test_wiki_usage_is_included(self):
        self.assertEqual(self.kinds("key_doc"), [("запись", "Док")])

    def test_unused_key_has_no_usage(self):
        self.assertEqual(key_usage("key_idle"), [])

    def test_used_slugs_outside_wiki(self):
        self.assertEqual(used_slugs(), {"key_a", "key_x", "key_prof", "key_file"})

    def test_dashboard_does_not_call_machine_and_file_keys_unused(self):
        unused = {k.slug for k in dashboard.build().unused_keys}
        self.assertEqual(unused, {"key_ab", "key_idle"})


@override_settings(FORCE_SCRIPT_NAME=None)
class KeyPageTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(get_user_model().objects.create_superuser("root", password="pw"))

    def test_key_page_lists_every_kind_with_links(self):
        key = key_item("key_a")
        machine = Machine.objects.create(name="Main", hostname="main")
        app = make_app(machine, "wiki", "W", "/apps/wiki/", key_condition="key_a")
        item = embed_key(make_file(machine, "/s.txt").item, "key_a").item
        response = self.client.get(reverse("admin:filesystem_item_change", args=[key.pk]))
        self.assertContains(response, reverse("admin:filesystem_item_change", args=[app.item.pk]))
        self.assertContains(response, "объект: <a")

    def test_unused_key_message(self):
        key = key_item("idle")
        response = self.client.get(reverse("admin:filesystem_item_change", args=[key.pk]))
        self.assertContains(response, "Нигде: ни в вики, ни в условиях машин")
