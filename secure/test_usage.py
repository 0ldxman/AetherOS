"""Где используется ключ: вики, машины, файлы.

Запуск: python manage.py test secure.test_usage
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.models import FileKey, MachineFile
from machines.models import Machine, MachineApp, MachineProfile
from secure.models import Key
from secure.usage import key_usage, used_slugs
from wiki import dashboard
from wiki.models import Document


class UsageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for slug in ("key_a", "key_ab", "key_idle", "key_file", "key_prof", "key_doc"):
            Key.objects.create(slug=slug)
        machine = Machine.objects.create(name="Main", hostname="main")
        MachineApp.objects.create(
            machine=machine, label="wiki", glyph="W", path="/apps/wiki/",
            key_condition={"all": ["key_a", {"not": "key_x"}]},
        )
        MachineProfile.objects.create(machine=machine, name="P", login="l", freq=1, key_condition="key_prof")
        file = MachineFile.objects.create(machine=machine, path="/secret.txt")
        FileKey.objects.create(file=file, key=Key.objects.get(slug="key_file"))
        Document.objects.create(title="Док", body="[x]{key_doc}")

    def kinds(self, slug):
        return sorted((u.kind, u.label) for u in key_usage(slug))

    def test_app_condition_counts(self):
        self.assertEqual(self.kinds("key_a"), [("приложение", "main: wiki")])

    def test_exact_slug_not_substring(self):
        self.assertEqual(self.kinds("key_ab"), [])

    def test_profile_condition_counts(self):
        self.assertEqual(self.kinds("key_prof"), [("профиль", "l@main:1.000")])

    def test_file_key_counts(self):
        self.assertEqual(self.kinds("key_file"), [("файл", "main:/secret.txt")])

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
        key = Key.objects.create(slug="key_a")
        machine = Machine.objects.create(name="Main", hostname="main")
        app = MachineApp.objects.create(
            machine=machine, label="wiki", glyph="W", path="/apps/wiki/", key_condition="key_a"
        )
        file = MachineFile.objects.create(machine=machine, path="/s.txt")
        FileKey.objects.create(file=file, key=key)
        response = self.client.get(reverse("admin:secure_key_change", args=[key.pk]))
        self.assertContains(response, "приложение: <a")
        self.assertContains(response, reverse("admin:machines_machineapp_change", args=[app.pk]))
        self.assertContains(response, "файл: <a")

    def test_unused_key_message(self):
        key = Key.objects.create(slug="idle")
        response = self.client.get(reverse("admin:secure_key_change", args=[key.pk]))
        self.assertContains(response, "Нигде: ни в вики, ни в условиях машин")
