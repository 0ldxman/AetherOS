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


@override_settings(FORCE_SCRIPT_NAME=None)
class CreateAndSystemsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        cls.system, _ = SystemType.objects.get_or_create(code="AETHER", defaults={"name": "Aether"})
        Group.objects.filter(system_type=cls.system).delete()
        cls.core = Machine.objects.create(name="Core", hostname="aether-core")
        MachineProfile.objects.create(machine=cls.core, login="ops", name="Ops", freq=14)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    call = MachinePartsTests.call

    def test_a_machine_is_made_from_nothing_from_a_template_and_like_another(self):
        from filesystem.models import VolumeTemplate

        status, made = self.call("post", "/machines", {"hostname": "gw-01"})
        self.assertEqual(status, 200, made)
        template = VolumeTemplate.objects.create(name="unix", folders="etc\nhome")
        self.assertIn("unix", [t["name"] for t in self.call("get", "/templates")[1]])
        made = self.call("post", "/machines", {"hostname": "gw-02", "root": "template", "template": template.pk})[1]
        self.assertEqual(Machine.objects.get(pk=made["id"]).mounts.count(), 1)
        made = self.call("post", "/machines", {"hostname": "aether-edge", "root": "like", "like": self.core.pk})[1]
        self.assertEqual(list(Machine.objects.get(pk=made["id"]).profiles.values_list("login", flat=True)), ["ops"])
        status, answer = self.call("post", "/machines", {"hostname": "aether-core"})
        self.assertEqual(status, 400)
        self.assertIn("hostname", answer["fields"])

    def test_a_system_machine_is_not_deleted(self):
        Machine.objects.filter(pk=self.core.pk).update(is_system=True)
        self.assertEqual(self.call("delete", f"/machines/{self.core.pk}")[0], 400)
        other = Machine.objects.create(name="Tmp", hostname="tmp")
        self.assertEqual(self.call("delete", f"/machines/{other.pk}")[0], 200)
        self.assertFalse(Machine.objects.filter(pk=other.pk).exists())

    def test_a_system_type_shows_default_places_and_groups_and_keeps_them_when_edited(self):
        data = self.call("get", "/systems/AETHER")[1]
        places = {row["name"]: row for row in data["places"]}
        self.assertEqual((places["home"]["path"], places["home"]["default"]), ("", "/home/{login}"))
        self.assertEqual([(g["name"], g["source"]) for g in data["groups"]], [("users", "default")])

        data = self.call("put", "/systems/AETHER/groups/ops", {"privileges": ["clock"]})[1]
        self.assertEqual([(g["name"], g["source"]) for g in data["groups"]], [("ops", "system"), ("users", "system")])
        data = self.call("put", "/systems/AETHER/places", {"places": {"home": "/users/{login}", "logs": ""}})[1]
        places = {row["name"]: row for row in data["places"]}
        self.assertEqual((places["home"]["path"], places["logs"]["path"]), ("/users/{login}", ""))
        self.assertEqual(self.call("get", "/systems")[1][0]["machines"], 1)

    def test_a_system_code_can_be_changed_and_takes_the_machines_along(self):
        SystemType.objects.create(code="OTHER", name="Other")
        status, data = self.call("put", "/systems/AETHER", {"code": "other", "name": "Aether"})
        self.assertEqual(status, 400)
        status, data = self.call("put", "/systems/AETHER", {"code": "nova", "name": "Nova"})
        self.assertEqual((status, data["code"]), (200, "NOVA"))
        self.core.refresh_from_db()
        self.assertEqual(self.core.system, "NOVA")
        self.assertEqual(data["machines"], [self.core.hostname])

    def test_the_greeting_of_an_os_is_validated_previewed_and_shown(self):
        body = {"name": "Aether", "greeting": "Hi <success>{login}</success> on {host}\n{nope}"}
        status, data = self.call("put", "/systems/AETHER", body)
        self.assertEqual(status, 400)
        body["greeting"] = "Hi <success>{login}</success> on {host}"
        status, data = self.call("put", "/systems/AETHER", body)
        self.assertEqual((status, data["greeting"]), (200, body["greeting"]))
        status, data = self.call("post", "/systems/AETHER/greeting/preview", {"greeting": "<dim>{os}</dim> {host}\n{x}"})
        self.assertEqual([part["text"] for part in data["lines"][0]], ["AETHER", f" {self.core.hostname}"])
        self.assertEqual([e["line"] for e in data["errors"]], [2])
        from terminal.scenes.shell import greeting_scene
        from machines.world.identity import identity_of
        system = SystemType.objects.get(code="AETHER")
        shown = [s.get("value") for s in greeting_scene(identity_of(self.core.hostname), "ivan", None, system) if s["op"] == "text"]
        self.assertEqual(shown, ["Hi ", "ivan", f" on {self.core.hostname}"])

    def test_the_greeting_takes_real_facts_and_random_numbers(self):
        from datetime import timedelta

        from django.utils import timezone

        from machines.world.facts import facts
        from machines.world.identity import identity_of

        self.core.note = "Check the vault"
        self.core.booted_at = timezone.now() - timedelta(days=2, hours=3)
        self.core.save()
        known = facts(self.core)
        self.assertEqual((known["accounts"], known["note"], known["last_login"]), (self.core.profiles.count(), "Check the vault", "never"))
        self.assertTrue(known["uptime"].startswith("2 days"))
        status, data = self.call("post", "/systems/AETHER/greeting/preview", {"greeting": "<rand>5-5</rand> % {note} {serial}"})
        self.assertEqual("".join(part["text"] for part in data["lines"][0]), f"5 % Check the vault {identity_of(self.core.hostname).serial}")
        self.assertEqual(self.call("post", "/systems/AETHER/greeting/preview", {"greeting": "<rand>x</rand>"})[1]["errors"][0]["line"], 1)

    def test_a_blackout_takes_the_os_values_over_the_engine_ones(self):
        from machines.world import blackout

        profile = self.core.profiles.first() or MachineProfile.objects.create(machine=self.core, login="guest", freq="1")
        shown = blackout.resolve("arrive", profile)
        self.assertEqual((shown["tone"], shown["title"]), ("success", f"{profile.login}@{self.core.hostname} - connection established"))
        status, data = self.call("put", "/systems/AETHER/blackouts/arrive", {"title": "{host}", "text": "hello {login}", "tone": "warning", "hold_ms": 100})
        self.assertEqual(status, 200)
        row = {r["event"]: r for r in data["blackouts"]}["arrive"]
        self.assertEqual((row["own"]["tone"], row["default"]["tone"]), ("warning", "success"))
        shown = blackout.resolve("arrive", profile)
        self.assertEqual((shown["title"], shown["text"], shown["tone"], shown["hold"], shown["delay"]), (self.core.hostname, f"hello {profile.login}", "warning", 100, 500))
        self.assertEqual(blackout.resolve("arrive", profile, "own text")["text"], "own text")
        self.assertEqual(self.call("put", "/systems/AETHER/blackouts/arrive", {"text": "<dim>x</dim>"})[0], 400)
        self.assertEqual(self.call("put", "/systems/AETHER/blackouts/arrive", {"text": "{nope}"})[0], 400)
        self.assertEqual(self.call("put", "/systems/AETHER/blackouts/arrive", {})[0], 200)
        self.assertEqual(blackout.resolve("arrive", profile)["tone"], "success")

    def test_the_identity_of_a_machine_can_be_typed_or_generated(self):
        from machines.world.identity import generate_host_key

        data = self.call("get", f"/machines/{self.core.pk}")[1]
        self.assertEqual((data["address"], data["host_key"], len(data["randomart"])), ("", "", 11))
        key = self.call("post", "/machines/generate", {"field": "host_key"})[1]["value"]
        self.assertTrue(key.startswith("SHA256:"))
        self.assertEqual(self.call("post", "/machines/generate", {"field": "nope"})[0], 400)
        self.assertRegex(self.call("post", "/machines/generate", {"field": "address", "system": "AETHER"})[1]["value"], r"^\d{1,2}\.\d{3}$")
        art = self.call("post", "/machines/randomart", {"host_key": key})[1]
        self.assertEqual((art["valid"], len(art["lines"])), (True, 11))
        self.assertFalse(self.call("post", "/machines/randomart", {"host_key": "oops"})[1]["valid"])

        body = {"hostname": "aether-core", "name": "Core", "system": "AETHER", "status": "ONLINE", "hid": "AA:BB:CC:DD:EE:FF",
                "address": "14.230", "serial": "AE-1111-2222-3", "host_key": key}
        data = self.call("put", f"/machines/{self.core.pk}", body)[1]
        self.assertEqual((data["hid"], data["address"], data["host_key"]), ("aa:bb:cc:dd:ee:ff", "14.230", key))
        self.assertEqual(self.call("put", f"/machines/{self.core.pk}", {**body, "host_key": "oops"})[0], 400)
        twin = Machine.objects.create(name="Twin", hostname="twin", hid="aa:bb:cc:dd:ee:ff")        # клон с тем же hid
        self.core.refresh_from_db()
        self.assertEqual(twin.hid, self.core.hid)

    def test_world_settings_drive_dates_and_the_greeting(self):
        from machines.world.dates import days_since, world

        data = self.call("get", "/world")[1]
        self.assertEqual((data["stations_known"], data["core_last_contact"]), (31, "2027-10-29"))
        data["game_now"], data["stations_reachable"] = "2030-11-15T03:14:00Z", 20
        self.assertEqual(self.call("put", "/world", data)[0], 200)
        self.assertEqual(days_since(world().core_last_contact), "1,113")
        status, shown = self.call("post", "/systems/AETHER/greeting/preview", {"greeting": "{date} {time} <since>2027-10-29</since>"})
        self.assertEqual(shown["errors"], [])
        self.assertEqual("".join(part["text"] for part in shown["lines"][0]), "2030-11-15 03:14 UTC 1,113")
        self.assertEqual(self.call("post", "/systems/AETHER/greeting/preview", {"greeting": "{core_days}"})[1]["errors"][0]["line"], 1)

    def test_since_counts_from_the_world_time_in_the_greeting_and_the_blackout(self):
        status, shown = self.call("post", "/systems/AETHER/greeting/preview", {"greeting": "<since>2027-10-29 | days</since> / <since>x</since>"})
        self.assertEqual("".join(part["text"] for part in shown["lines"][0]), "1,112 / ?")
        self.assertEqual([e["line"] for e in shown["errors"]], [1])
        self.assertEqual(self.call("put", "/systems/AETHER/blackouts/leave", {"text": "away <since>2027-10-29 | years</since> y"})[0], 200)
        from machines.world import blackout

        profile = self.core.profiles.first() or MachineProfile.objects.create(machine=self.core, login="guest", freq="1")
        self.assertEqual(blackout.resolve("leave", profile)["text"], "away 3 y")

    def test_a_scene_script_is_stored_previewed_bound_to_an_os_and_played_instead_of_the_built_in(self):
        from terminal.scenes.bridge import unreachable_scene

        status, made = self.call("post", "/scenes", {"slug": "gone", "title": "Gone", "body": "@task looking for {host} | FAIL | 100\nnothing there"})
        self.assertEqual((status, made["errors"]), (200, []))
        self.assertEqual(self.call("post", "/scenes", {"slug": "bad", "body": "@nope"})[0], 400)
        steps = self.call("post", "/scenes/preview", {"body": "@task {host} | OK", "slot": "bridge.unreachable"})[1]
        self.assertEqual(steps["steps"][0]["label"], "aether-core ")
        self.assertEqual(self.call("post", "/scenes/preview", {"body": "{login}", "slot": "bridge.unreachable"})[1]["errors"][0]["line"], 1)

        self.assertNotIn("looking", str(unreachable_scene("AETHER", "ghost")))
        data = self.call("put", "/systems/AETHER/scenes/bridge.unreachable", {"script": "gone"})[1]
        self.assertEqual({row["slot"]: row["script"] for row in data["scenes"]}["bridge.unreachable"], "gone")
        self.assertEqual(self.call("put", "/systems/AETHER/scenes/bridge.locked", {"script": "gone"})[0], 200)   # без подстановок host подходит и этому
        steps = unreachable_scene("AETHER", "ghost")
        self.assertEqual(steps[0]["label"], "looking for ghost ")
        self.assertEqual(self.call("delete", "/scenes/gone")[0], 400)             # назначена событию
        self.call("put", "/systems/AETHER/scenes/bridge.unreachable", {"script": None})
        self.call("put", "/systems/AETHER/scenes/bridge.locked", {"script": None})
        self.assertNotIn("looking", str(unreachable_scene("AETHER", "ghost")))
        self.assertEqual(self.call("delete", "/scenes/gone")[0], 200)
        broken = self.call("post", "/scenes", {"slug": "uses-login", "body": "{login}"})[1]
        self.assertEqual(self.call("put", "/systems/AETHER/scenes/bridge.unreachable", {"script": "uses-login"})[0], 400)  # логина у события нет

    def test_the_system_image_is_laid_under_the_machine_mounts(self):
        from filesystem.machine_view import MachineView

        base = Volume.objects.create(slug="base-image", name="Base")
        own = Volume.objects.create(slug="own-disk", name="Own")
        status, data = self.call("post", "/systems/AETHER/image", {"volume": base.pk, "mount_path": "/", "order": 5})
        self.assertEqual((status, [(r["volume"]["id"], r["mount_path"]) for r in data["image"]]), (200, [(base.pk, "/")]))
        self.assertEqual(self.call("post", "/systems/AETHER/image", {"volume": base.pk, "mount_path": ""})[0], 400)
        MachineMount.objects.create(machine=self.core, volume=own, mount_path="/", order=0)
        layers = MachineView(self.core, None, None).layers
        self.assertEqual([l.mount.volume_id for l in layers], [base.pk, own.pk])
        self.assertEqual([m["volume"]["id"] for m in self.call("get", f"/machines/{self.core.pk}/disks")[1]["inherited"]], [base.pk])
        row = data["image"][0]["id"]
        self.assertEqual(self.call("put", f"/systems/AETHER/image/{row}", {"volume": base.pk, "mount_path": "/srv", "order": 1})[1]["image"][0]["mount_path"], "/srv")
        self.assertEqual(self.call("delete", f"/systems/AETHER/image/{row}")[1]["image"], [])

    def test_the_first_machine_group_keeps_the_default_ones(self):
        data = self.call("put", f"/machines/{self.core.pk}/groups/night", {"privileges": ["backup"]})[1]
        self.assertEqual(sorted(row["name"] for row in data["groups"]), ["night", "users"])
