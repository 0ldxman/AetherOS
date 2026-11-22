"""Пульт мира в Студии: метки, счётчики, триггеры с условием строкой, журнал, сборка ключа."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from filesystem.models import KEY_FORMAT, Item
from team.testing import full_role

API = "/studio/api/world/state"


class WorldStateApiTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))

    def call(self, method, path="", body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"{API}{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def test_the_console(self):
        self.assertEqual(self.call("post", "/flags", {"name": "Bad Name"})[0], 400)
        self.call("post", "/counters", {"name": "fragments", "label": "фрагменты", "mode": "players"})
        status, data = self.call("post", "/triggers", {"name": "act-2", "condition_text": "world:fragments>=7 and not world:sealed",
                                                       "actions": [{"do": "world_flag", "name": "act-2"}]})
        self.assertEqual(status, 200)
        self.assertEqual(data["triggers"][0]["condition"], {"all": ["world:fragments>=7", {"not": "world:sealed"}]})
        self.assertEqual(data["counters"][0]["thresholds"], [{"value": 7, "op": ">=", "trigger": "act-2"}])
        self.assertEqual(self.call("post", "/triggers", {"name": "x", "condition_text": "secret-key", "actions": [{"do": "world_flag", "name": "y"}]})[0], 400)
        self.assertEqual(self.call("post", "/triggers", {"name": "x", "condition_text": "world:a", "actions": []})[0], 400)
        data = self.call("post", "/counters/fragments/set", {"value": 7})[1]
        self.assertEqual([f["name"] for f in data["flags"] if f["on"]], ["act-2"])
        self.assertTrue(data["events"][0]["text"])
        trigger = data["triggers"][0]["id"]
        self.assertEqual(self.call("post", f"/triggers/{trigger}/fire")[1]["triggers"][0]["fired_count"], 2)
        data = self.call("post", "/flags", {"name": "act-2", "on": False})[1]
        self.assertFalse(data["flags"][0]["on"])
        self.assertEqual(self.call("delete", f"/triggers/{trigger}")[1]["triggers"], [])

    def test_a_key_recipe(self):
        Item.objects.create(slug="vault-door", name="vault door", format=KEY_FORMAT)
        status, data = self.call("post", "/keys/vault-door/split", {"count": 3})
        self.assertEqual((status, [p["slug"] for p in data["parts"]]), (200, ["vault-door.1", "vault-door.2", "vault-door.3"]))
        self.assertEqual(self.call("get", "/keys/vault-door.2/recipe")[1]["part_of"], [["vault-door", "2 из 3"]])
        self.assertEqual(self.call("put", "/keys/vault-door/recipe", {"parts": ["vault-door.1"]})[0], 400)
        self.assertEqual(self.call("put", "/keys/vault-door/recipe", {"parts": []})[1]["parts"], [])


class UsesTests(TestCase):
    def setUp(self):
        from team.testing import full_role

        self.boss = get_user_model().objects.create_user("boss", is_staff=True, role=full_role())
        self.client.force_login(self.boss)

    def test_names_are_found_in_scenarios_by_value_or_condition(self):
        from graph.models import Graph

        self.client.post("/studio/api/world/state/flags", {"name": "core-online", "label": "", "on": False}, content_type="application/json")
        self.client.post("/studio/api/world/state/counters", {"name": "fragments", "label": ""}, content_type="application/json")
        Graph.objects.create(slug="a", title="Alpha", doc={"nodes": [{"id": "n", "type": "do:world_flag", "data": {"name": "core-online"}}], "wires": []})
        Graph.objects.create(slug="b", title="Beta", doc={"nodes": [{"id": "c", "type": "check", "data": {"condition": "world:fragments>=7 and tag:x"}}], "wires": []})
        Graph.objects.create(slug="c", title="Gamma", doc={"nodes": [{"id": "t", "type": "note", "data": {"text": "nothing here"}}], "wires": []})
        found = self.client.get("/studio/api/world/state/uses").json()
        self.assertEqual({name: [g["title"] for g in graphs] for name, graphs in found.items()}, {"core-online": ["Alpha"], "fragments": ["Beta"]})
