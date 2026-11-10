"""Файлы машины: вид всей файловой системы и правки, которые ложатся в один диск отличий.

Запуск: python manage.py test studio.tests.test_machine_files
"""
from team.testing import full_role
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.models import FileFormat, Item, Placement, Volume
from machines.models import Machine, MachineMount


@override_settings(FORCE_SCRIPT_NAME=None)
class MachineFilesApiTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))
        FileFormat.objects.get_or_create(name="txt", defaults={"extension": ".txt"})
        self.core = Machine.objects.create(name="Core", hostname="core")
        self.edge = Machine.objects.create(name="Edge", hostname="edge")
        self.base = Volume.objects.create(slug="base")
        hosts = Item.objects.create(slug="hosts", name="hosts", format="txt", body="base hosts")
        Placement.objects.create(volume=self.base, kind="item", item=hosts, name="hosts")
        etc = Placement.objects.create(volume=self.base, kind="folder", name="etc")
        Placement.objects.create(volume=self.base, kind="file", parent=etc, name="motd.xyz", content="hello")
        for machine in (self.core, self.edge):
            MachineMount.objects.create(machine=machine, volume=self.base, mount_path="/", order=0)

    def call(self, method, path, body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"/studio/api/machines/{self.core.pk}/{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def rows(self):
        return {r["path"]: r for r in self.call("get", "files")[1]["rows"]}

    def test_the_tree_shows_every_file_with_where_it_comes_from(self):
        data = self.call("get", "files")[1]
        rows = {r["path"]: r for r in data["rows"]}
        self.assertEqual((rows["/hosts"]["volume"], rows["/hosts"]["kind"], data["overlay"], data["changed"]), ("base", "file", None, 0))
        self.assertIsNone(rows["/etc/motd.xyz"]["item"])          # файл без объекта

    def test_opening_an_object_of_the_base_makes_a_copy_for_this_machine_only(self):
        status, opened = self.call("post", "files/open", {"path": "/hosts"})
        self.assertEqual((status, opened["kind"]), (200, "item"))
        copy = Item.objects.get(pk=opened["item"])
        self.assertNotEqual(copy.slug, "hosts")
        rows = self.rows()
        self.assertEqual((rows["/hosts"]["mark"], rows["/hosts"]["volume"]), ("override", "core-own"))
        self.assertEqual(self.call("get", "files")[1]["changed"], 1)
        edge = self.client.get(f"/studio/api/machines/{self.edge.pk}/files").json()["rows"]
        self.assertEqual({r["path"]: r["volume"] for r in edge}["/hosts"], "base")                  # другая машина не затронута

    def test_a_text_only_file_of_the_base_can_be_overridden_too(self):
        status, opened = self.call("post", "files/open", {"path": "/etc/motd.xyz"})
        self.assertEqual((status, opened["kind"]), (200, "text"))
        placement = Placement.objects.get(pk=opened["placement"])
        self.assertEqual((placement.content, placement.volume.slug), ("hello", "core-own"))
        self.assertEqual(Placement.objects.get(volume=self.base, name="motd.xyz").content, "hello")  # общий файл не тронут
        again = self.call("post", "files/open", {"path": "/etc/motd.xyz"})[1]
        self.assertEqual(again["placement"], opened["placement"])                                    # повторно та же копия

    def test_a_new_file_has_no_object_and_any_extension(self):
        before = Item.objects.count()
        status, made = self.call("post", "files/file", {"parent": "/etc", "name": "notes.weird"})
        self.assertEqual((status, Item.objects.count()), (200, before))
        placement = Placement.objects.get(pk=made["placement"])
        self.assertEqual((placement.kind, placement.volume.slug), ("file", "core-own"))
        self.assertEqual(self.rows()["/etc/notes.weird"]["mark"], "added")
        self.assertEqual(self.call("post", "files/file", {"parent": "/etc", "name": "notes.weird"})[0], 400)    # имя занято

    def test_hide_restore_and_reset(self):
        self.call("post", "files/delete", {"path": "/hosts"})
        rows = self.rows()
        self.assertEqual(rows["/hosts"]["kind"], "deleted")
        self.assertEqual(self.call("post", "files/restore", {"path": "/hosts"})[0], 200)
        self.assertEqual(self.rows()["/hosts"]["kind"], "file")
        self.call("post", "files/open", {"path": "/hosts"})
        self.assertEqual(self.call("post", "files/reset", {"path": "/hosts"})[0], 200)
        self.assertEqual(self.rows()["/hosts"]["volume"], "base")

    def test_move_and_copy_files_between_folders(self):
        self.call("post", "files/folder", {"parent": "/", "name": "docs"})
        self.assertEqual(self.call("post", "files/move", {"path": "/hosts", "dest": "/docs"})[0], 200)
        rows = self.rows()
        self.assertEqual((rows["/docs/hosts"]["mark"], rows["/hosts"]["kind"]), ("added", "deleted"))
        self.assertEqual(self.call("post", "files/copy", {"path": "/etc/motd.xyz", "dest": "/docs"})[0], 200)
        self.assertEqual(self.rows()["/docs/motd.xyz"]["mark"], "added")
        self.assertEqual(self.call("post", "files/copy", {"path": "/etc/motd.xyz", "dest": "/docs"})[0], 200)
        self.assertIn("/docs/motd копия.xyz", self.rows())
        self.assertEqual(self.call("post", "files/move", {"path": "/etc", "dest": "/docs"})[0], 200)           # папка общего диска переезжает целиком
        rows = self.rows()
        self.assertEqual((rows["/docs/etc/motd.xyz"]["mark"], rows["/etc"]["kind"]), ("added", "deleted"))
        self.assertNotIn("/etc/motd.xyz", rows)
        self.assertEqual(self.client.get(f"/studio/api/machines/{self.edge.pk}/files").json()["rows"][-1]["volume"], "base")   # другая машина не тронута
        self.assertEqual(self.call("post", "files/move", {"path": "/docs", "dest": "/docs/x"})[0], 400)

    def test_rename_and_rights(self):
        self.assertEqual(self.call("post", "files/rename", {"path": "/hosts", "name": "hosts.old"})[0], 200)
        self.assertIn("/hosts.old", self.rows())
        self.assertEqual(self.call("post", "files/rights", {"path": "/hosts.old", "owner": "root", "group": "root", "mode": "640"})[0], 200)
        row = self.rows()["/hosts.old"]
        self.assertEqual((row["owner"], row["group"], row["mode"]), ("root", "root", "640"))

    def test_protection_of_a_shared_file_goes_to_a_copy_for_this_machine(self):
        status, target = self.call("post", "files/protect", {"path": "/hosts"})
        self.assertEqual(status, 200)
        self.assertNotEqual(Item.objects.get(pk=target["item"]).slug, "hosts")
        self.assertEqual(Placement.objects.get(pk=target["placement"]).volume.slug, "core-own")
        status, _ = self.client.put(
            f"/studio/api/items/{target['item']}/placements/{target['placement']}/protection",
            data=json.dumps({"access_mode": "replace", "access": "root", "state_mode": "inherit", "state": ""}), content_type="application/json").status_code, None
        self.assertEqual(status, 200)
        self.assertTrue(self.rows()["/hosts"]["condition"])
        edge = self.client.get(f"/studio/api/machines/{self.edge.pk}/files").json()["rows"]
        self.assertFalse({r["path"]: r for r in edge}["/hosts"]["condition"])
