"""Графы у вещей: заводятся по вещи, решают попытку сразу, без ожиданий; в списке сценариев их нет."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from graph import check, owned
from graph.tests.test_runtime import node, wire
from machines.models import Machine


class OwnedTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.core = Machine.objects.create(name="Core", hostname="core")

    def test_one_graph_per_machine_found_by_host(self):
        first = owned.ensure("machine", "CORE")
        self.assertEqual(first.owner, f"machine:{self.core.pk}")
        self.assertEqual(owned.ensure("machine", self.core), first)
        self.assertEqual(first.doc["nodes"][0]["type"], "attempt:machine")
        self.assertIsNone(owned.ensure("machine", "nowhere"))

    def test_no_graph_or_no_answer_leaves_it_to_the_machine(self):
        self.assertIsNone(owned.decide("machine", self.core, self.ivan))
        owned.ensure("machine", self.core)
        self.assertIsNone(owned.decide("machine", self.core, self.ivan))
        graph = owned.ensure("machine", self.core)
        graph.doc = {"nodes": [node("start", "attempt:machine"), node("a", "answer", mode="deny", text="{login} no")],
                     "wires": [wire("start", "go", "a")]}
        graph.save()
        self.assertEqual(owned.decide("machine", self.core, self.ivan, login="guest")["text"], "guest no")

    def test_waiting_is_not_allowed_inside(self):
        doc = {"nodes": [node("start", "attempt:machine"), node("w", "wait", minutes=5), node("a", "answer")],
               "wires": [wire("start", "go", "w"), wire("w", "next", "a")]}
        texts = [p["text"] for p in check.problems(doc, "x", owner="machine:1")]
        self.assertIn("в графе попытки нельзя ждать: решение принимается сразу", texts)
        self.assertFalse(any("нет старта" in t for t in texts))

    def test_api_lists_without_owned_and_opens_by_host(self):
        from team.testing import full_role

        boss = get_user_model().objects.create_user("boss", is_staff=True, role=full_role())
        self.client.force_login(boss)
        missing = self.client.get("/studio/api/world/graphs/owned", {"kind": "machine", "key": "core"}).json()
        self.assertIsNone(missing["id"])
        made = self.client.get("/studio/api/world/graphs/owned", {"kind": "machine", "key": "core", "create": "true"}).json()
        self.assertIsNotNone(made["id"])
        self.assertEqual(self.client.get("/studio/api/world/graphs").json(), [])
        self.assertEqual(self.client.get(f"/studio/api/world/graphs/{made['id']}").json()["owner"], f"machine:{self.core.pk}")
