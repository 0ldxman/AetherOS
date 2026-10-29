"""API студии: группы машины, политики входа, диски и дерево «глазами учётки».

Запуск: python manage.py test studio.tests.test_machine_parts
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.testing import make_file
from filesystem.models import Volume
from machines.models import EntryPolicy, Export, Group, Machine, MachineMount, MachineProfile, SystemType

API = "/studio/api"


@override_settings(FORCE_SCRIPT_NAME=None)
class MachinePartsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        cls.system, _ = SystemType.objects.get_or_create(code="AETHER", defaults={"name": "Aether"})
        cls.core = Machine.objects.create(name="Core", hostname="aether-core")
        cls.archive = Machine.objects.create(name="Archive", hostname="archive-srv")
        Group.objects.filter(system_type=cls.system).delete()
        Group.objects.create(system_type=cls.system, name="users", privileges=["bridge"], everyone=True)
        Group.objects.create(system_type=cls.system, name="ops", privileges=["clock", "mount"])
        cls.ivan = MachineProfile.objects.create(machine=cls.core, login="ivan", name="Ivan", freq=1, groups=["ops"])
        cls.anna = MachineProfile.objects.create(machine=cls.core, login="anna", name="Anna", freq=1)
        cls.reader = MachineProfile.objects.create(machine=cls.archive, login="reader", name="Reader", freq=1)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def call(self, method, path, body=None):
        response = getattr(self.client, method)(API + path, data=json.dumps(body) if body is not None else None, content_type="application/json")
        return response.status_code, (response.json() if response.content else None)

    def rows(self, data):
        return {row["name"]: row for row in data["groups"]}

    # ---- группы ---------------------------------------------------------------------------------------------------

    def test_the_groups_show_where_they_come_from_and_who_is_in(self):
        data = self.call("get", f"/machines/{self.core.pk}/groups")[1]
        self.assertIn("clock", [p["code"] for p in data["privileges"]])
        rows = self.rows(data)
        self.assertEqual((rows["users"]["source"], rows["users"]["members"]), ("system", ["anna", "ivan"]))
        self.assertEqual(rows["ops"]["members"], ["ivan"])

    def test_the_machine_overrides_disables_and_reverts_a_group(self):
        rows = self.rows(self.call("put", f"/machines/{self.core.pk}/groups/ops", {"privileges": ["clock"]})[1])
        self.assertEqual((rows["ops"]["source"], rows["ops"]["overrides"], rows["ops"]["privileges"]), ("machine", True, ["clock"]))
        rows = self.rows(self.call("post", f"/machines/{self.core.pk}/groups/users/disable")[1])
        self.assertEqual((rows["users"]["disabled"], rows["users"]["members"]), (True, []))
        rows = self.rows(self.call("delete", f"/machines/{self.core.pk}/groups/users")[1])
        self.assertFalse(rows["users"]["disabled"])
        rows = self.rows(self.call("put", f"/machines/{self.core.pk}/groups/night", {"privileges": ["backup"], "everyone": False})[1])
        self.assertEqual((rows["night"]["source"], rows["night"]["overrides"]), ("machine", False))
        self.assertEqual(self.call("put", f"/machines/{self.core.pk}/groups/x", {"privileges": ["fly"]})[0], 400)

    # ---- политики -------------------------------------------------------------------------------------------------

    def test_a_policy_is_made_shows_its_week_and_names_a_bad_window_line(self):
        status, policy = self.call("post", "/policies", {"name": "office", "windows": "mon-fri: 9:00-13:00", "sources": "gw-*"})
        self.assertEqual(status, 200, policy)
        self.assertEqual([slot for slot, open_ in enumerate(policy["grid"][0]) if open_], list(range(18, 26)))
        status, answer = self.call("put", f"/policies/{policy['id']}", {**policy, "windows": "mon-fri 9:00"})
        self.assertEqual(status, 400)
        self.assertIn("windows", answer["fields"])
        week = self.call("post", "/policies/week", {"windows": "sat: 10:00-12:00"})[1]
        self.assertTrue(week["grid"][5][20])
        self.assertTrue(self.call("post", "/policies/week", {"windows": "funday: 1:00-2:00"})[1]["error"])

    def test_a_used_policy_lists_where_and_is_not_deleted(self):
        policy = EntryPolicy.objects.create(name="strict")
        self.ivan.entry_policy = policy
        self.ivan.save()
        data = self.call("get", f"/policies/{policy.pk}")[1]
        self.assertEqual([w["label"] for w in data["used_by"]], ["ivan@aether-core"])
        self.assertEqual(self.call("get", "/policies")[1][0]["accounts"], 1)
        self.assertEqual(self.call("delete", f"/policies/{policy.pk}")[0], 400)

    # ---- диски ----------------------------------------------------------------------------------------------------

    def test_mounts_and_exports_are_edited_with_their_rules(self):
        volume = Volume.objects.create(slug="harbor", name="Harbor")
        status, data = self.call("post", f"/machines/{self.core.pk}/mounts", {"mode": "local", "volume": volume.pk, "mount_path": "mnt/harbor"})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["mounts"][0]["mount_path"], "/mnt/harbor")
        status, answer = self.call("post", f"/machines/{self.core.pk}/mounts", {"mode": "remote", "host": self.archive.pk, "mount_path": "/mnt/far"})
        self.assertEqual(status, 400)
        self.assertIn("host_path", answer["fields"])
        status, data = self.call("post", f"/machines/{self.core.pk}/mounts", {
            "mode": "remote", "host": self.archive.pk, "host_path": "/srv", "account": self.reader.pk, "mount_path": "/mnt/far",
        })
        remote = next(m for m in data["mounts"] if m["mode"] == "remote")
        self.assertEqual((status, remote["account"]["label"], remote["host"]["label"]), (200, "reader", "archive-srv"))
        data = self.call("post", f"/machines/{self.archive.pk}/exports", {"path": "srv/harbor"})[1]
        self.assertEqual([e["path"] for e in data["exports"]], ["/srv/harbor"])
        self.assertEqual(self.call("delete", f"/machines/{self.archive.pk}/exports/{data['exports'][0]['id']}")[1]["exports"], [])

    def test_the_tree_shows_what_an_account_can_read(self):
        make_file(self.core, "/home/ivan/notes.txt", body="мои заметки")
        make_file(self.core, "/home/anna/diary.txt", body="личное")
        make_file(self.core, "/etc/motd", body="welcome")
        listing = self.call("get", f"/machines/{self.core.pk}/tree?account={self.anna.pk}&path=/home")[1]
        nodes = {node["name"]: node for node in listing["nodes"]}
        self.assertEqual((nodes["anna"]["readable"], nodes["ivan"]["readable"]), (True, False))           # чужой дом 700
        self.assertEqual(nodes["ivan"]["mode"], "700")
        denied = self.call("get", f"/machines/{self.core.pk}/tree?account={self.anna.pk}&path=/home/ivan")[1]
        self.assertEqual((denied["readable"], denied["nodes"]), (False, []))
        own = self.call("get", f"/machines/{self.core.pk}/tree?account={self.ivan.pk}&path=/home/ivan")[1]
        self.assertEqual([node["name"] for node in own["nodes"]], ["notes.txt"])
