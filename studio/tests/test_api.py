"""API студии: вход только для сотрудников, тома и дерево, объект с версией и занятием, предпросмотр.

Запуск: python manage.py test studio
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.models import FileFormat, Item, Placement, Volume

API = "/studio/api"


@override_settings(FORCE_SCRIPT_NAME=None)
class StudioApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.boss = users.objects.create_user("boss", password="pw", is_staff=True)
        cls.other = users.objects.create_user("anna", password="pw", is_staff=True)
        cls.player = users.objects.create_user("ivan", password="pw")
        FileFormat.objects.update_or_create(name="rec", defaults={"extension": ".rec", "content": "text", "markup": True, "editable": True})
        FileFormat.objects.update_or_create(name="txt", defaults={"extension": ".txt", "kind": "text", "content": "text", "editable": True})
        cls.volume = Volume.objects.create(slug="harbor", name="Harbor")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def call(self, method, path, body=None, client=None):
        client = client or self.client
        response = getattr(client, method)(API + path, data=json.dumps(body) if body is not None else None, content_type="application/json")
        return response.status_code, (response.json() if response.content else None)

    def test_only_staff_gets_in(self):
        self.client.logout()
        self.assertEqual(self.call("get", "/me")[0], 401)
        self.client.force_login(self.player)
        self.assertEqual(self.call("get", "/volumes")[0], 401)
        self.client.force_login(self.boss)
        self.assertEqual(self.call("get", "/me"), (200, {"username": "boss", "superuser": False}))

    def test_a_write_needs_the_csrf_token(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.boss)
        self.assertEqual(self.call("post", f"/volumes/{self.volume.pk}/folders", {"name": "x"}, client=strict)[0], 403)

    def test_a_volume_is_built_and_listed(self):
        self.assertEqual(self.call("post", f"/volumes/{self.volume.pk}/folders", {"name": "ports"})[0], 200)
        folder = Placement.objects.get(volume=self.volume, name="ports")
        status, created = self.call("post", f"/volumes/{self.volume.pk}/files", {"parent": folder.pk, "name": "manifest.txt"})
        self.assertEqual(status, 200)
        self.assertEqual(Item.objects.get(pk=created["item"]).format, "txt")

        rows = self.call("get", "/volumes")[1]
        self.assertEqual([(r["slug"], r["files"], r["folders"]) for r in rows], [("harbor", 1, 1)])
        tree = self.call("get", f"/volumes/{self.volume.pk}")[1]
        self.assertEqual(sorted(r["name"] for r in tree["rows"]), ["manifest.txt", "ports"])

    def test_refusals_come_back_as_messages(self):
        self.call("post", f"/volumes/{self.volume.pk}/folders", {"name": "ports"})
        status, answer = self.call("post", f"/volumes/{self.volume.pk}/folders", {"name": "ports"})
        self.assertEqual(status, 400)
        self.assertIn("уже есть", answer["detail"])
        self.assertEqual(self.call("post", f"/volumes/{self.volume.pk}/folders", {"name": "a:b"})[0], 400)

    def test_a_placement_is_renamed_hidden_and_given_rights(self):
        self.call("post", f"/volumes/{self.volume.pk}/folders", {"name": "ports"})
        folder = Placement.objects.get(volume=self.volume, name="ports")
        status, _ = self.call("patch", f"/volumes/{self.volume.pk}/placements/{folder.pk}", {"name": "docks", "hidden": True, "mode": "750"})
        self.assertEqual(status, 200)
        folder.refresh_from_db()
        self.assertEqual((folder.name, folder.hidden, folder.mode), ("docks", True, "750"))

    def _item(self):
        status, created = self.call("post", f"/volumes/{self.volume.pk}/files", {"name": "report.rec"})
        return self.call("get", f"/items/{created['item']}")[1]

    def test_an_item_is_saved_with_its_version_and_a_stale_save_is_a_conflict(self):
        item = self._item()
        self.assertEqual((item["name"], item["format"], item["placements"][0]["path"]), ("report", "rec", "report.rec"))
        status, saved = self.call("put", f"/items/{item['id']}", {**item, "body": "Отчёт", "version": item["version"]})
        self.assertEqual((status, saved["body"], saved["updated_by"]), (200, "Отчёт", "boss"))

        status, conflict = self.call("put", f"/items/{item['id']}", {**item, "body": "старое", "version": item["version"]})
        self.assertEqual((status, conflict["by"]), (409, "boss"))
        status, forced = self.call("put", f"/items/{item['id']}", {**item, "body": "поверх", "version": item["version"], "force": True})
        self.assertEqual((status, forced["body"]), (200, "поверх"))
        self.assertEqual(len(self.call("get", f"/items/{item['id']}/revisions")[1]), 2)

    def test_a_bad_field_is_named(self):
        item = self._item()
        status, answer = self.call("put", f"/items/{item['id']}", {**item, "name": "a/b", "version": item["version"]})
        self.assertEqual(status, 400)
        self.assertIn("name", answer["fields"])

    def test_the_lock_shows_who_edits(self):
        item = self._item()
        self.assertEqual(self.call("post", f"/items/{item['id']}/lock")[0], 200)
        self.client.force_login(self.other)
        status, holder = self.call("post", f"/items/{item['id']}/lock")
        self.assertEqual((status, holder["user"]), (423, "boss"))
        self.assertEqual(self.call("get", f"/items/{item['id']}")[1]["holder"]["user"], "boss")
        self.client.force_login(self.boss)
        self.call("delete", f"/items/{item['id']}/lock")
        self.client.force_login(self.other)
        self.assertEqual(self.call("post", f"/items/{item['id']}/lock")[0], 200)

    def test_the_preview_draws_markup_and_names_the_problems(self):
        status, page = self.call("post", "/items/preview", {"format": "rec", "title": "R", "body": "::spoiler k\nтайна\n::\n\n::nosuch\n"})
        self.assertEqual(status, 200)
        self.assertIn("doc--rec", page["body"])
        self.assertNotIn("::spoiler", page["body"])
        self.assertTrue(page["issues"]["body"])
        plain = self.call("post", "/items/preview", {"format": "txt", "body": "::spoiler k"})[1]
        self.assertIn("::spoiler k", plain["body"])

    def test_the_shell_page_is_for_staff(self):
        self.assertEqual(self.client.get("/studio/").status_code, 200)
        self.client.force_login(self.player)
        self.assertEqual(self.client.get("/studio/").status_code, 302)
