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

    def test_a_new_volume_can_come_from_a_template_and_be_mounted(self):
        from filesystem.models import VolumeTemplate
        from machines.models import Machine, MachineMount

        template = VolumeTemplate.objects.create(name="small", folders="var/log\nhome")
        machine = Machine.objects.create(name="Core", hostname="core")
        status, made = self.call("post", "/volumes", {
            "slug": "core-root", "name": "Core root", "template": template.pk, "machine": machine.pk, "mount_path": "/",
        })
        self.assertEqual(status, 200)
        volume = Volume.objects.get(pk=made["id"])
        self.assertEqual(sorted(volume.placements.values_list("name", flat=True)), ["home", "log", "var"])
        self.assertEqual(list(MachineMount.objects.filter(volume=volume).values_list("machine", "mount_path")), [(machine.pk, "/")])
        self.assertEqual(self.call("post", "/volumes", {"slug": "core-root"})[0], 400)       # слаг занят

    def test_volume_properties_and_the_decorative_size(self):
        tree = self.call("get", f"/volumes/{self.volume.pk}")[1]
        self.assertEqual((tree["capacity_gb"], tree["used_gb"]), (None, None))
        body = {"slug": "harbor", "name": "Harbor disk", "label": "x", "uuid": tree["uuid"], "capacity_gb": 4000, "used_gb": 1700}
        status, saved = self.call("put", f"/volumes/{self.volume.pk}", body)
        self.assertEqual((status, saved["name"], saved["capacity_gb"], saved["used_gb"]), (200, "Harbor disk", 4000, 1700))
        self.assertEqual(self.call("put", f"/volumes/{self.volume.pk}", {**body, "used_gb": 5000})[0], 400)       # занято больше ёмкости
        self.assertEqual(self.call("put", f"/volumes/{self.volume.pk}", {**body, "uuid": "oops"})[0], 400)

    def test_the_greeting_counts_the_disks_of_a_machine(self):
        from machines.models import Machine, MachineMount
        from machines.world.facts import disks_text, size_text

        self.assertEqual((size_text(512), size_text(4000), size_text(1500), size_text(12000)), ("512 GB", "4 TB", "1.5 TB", "12 TB"))
        machine = Machine.objects.create(name="Core", hostname="core")
        self.assertIsNone(disks_text(machine))
        other = Volume.objects.create(slug="other", capacity_gb=1000, used_gb=250)
        Volume.objects.filter(pk=self.volume.pk).update(capacity_gb=3000, used_gb=750)
        MachineMount.objects.create(machine=machine, volume=self.volume, mount_path="/")
        MachineMount.objects.create(machine=machine, volume=other, mount_path="/mnt/other")
        self.assertEqual(disks_text(machine), ("4 TB", "1 TB", "25"))

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


class SchemaNamesTests(TestCase):
    def test_no_two_schemas_share_a_name(self):
        """В OpenAPI схема называется по имени класса: одноимённые классы разных файлов затёрли бы друг друга в типах фронта."""
        import importlib
        import pkgutil
        from collections import defaultdict

        from pydantic import BaseModel

        import studio.api as package

        found = defaultdict(set)
        for info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"studio.api.{info.name}")
            for name, value in vars(module).items():
                if isinstance(value, type) and issubclass(value, BaseModel) and value.__module__ == module.__name__:
                    found[name].add(info.name)
        self.assertEqual({name: files for name, files in found.items() if len(files) > 1}, {})
