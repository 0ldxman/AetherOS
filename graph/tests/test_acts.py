"""Действия по пространствам: нода с выбором варианта запускает своё действие движка с неизменными полями варианта."""
import itertools

from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from graph import check, nodes, runtime
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine


class ChoiceActionTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.core = Machine.objects.create(name="Core", hostname="core")
        self.seq = itertools.count()

    def run_one(self, kind, **data):
        graph = make([node("m", "manual"), node("a", kind, **data), node("ok", "do:world_count", name="ok"), node("no", "do:world_count", name="no")],
                     [wire("m", "fire", "a"), wire("a", "next", "ok"), wire("a", "fail", "no")], slug=f"g{next(self.seq)}")
        runtime.start_manual(graph, "m", self.ivan)
        return values.get("count", "world", 0, "ok"), values.get("count", "world", 0, "no")

    def test_variant_picks_the_engine_action_and_its_fixed_fields(self):
        self.assertEqual(self.run_one("act:machine.status", variant="stop", host="core"), (1, 0))
        self.core.refresh_from_db()
        self.assertTrue(self.core.halted)
        self.run_one("act:machine.status", variant="start", host="core")
        self.core.refresh_from_db()
        self.assertFalse(self.core.halted)

    def test_tag_and_count_choices(self):
        self.run_one("act:tag", variant="on", owner="player", name="met")
        self.assertTrue(values.on("player", self.ivan.pk, "met"))
        self.run_one("act:count", variant="set", owner="world", name="act", value=3)
        self.assertEqual(values.get("count", "world", 0, "act"), 3)

    def test_only_fields_of_the_chosen_variant_are_required(self):
        doc = {"nodes": [node("m", "manual"), node("a", "act:machine.status", variant="stop", host="core")], "wires": [wire("m", "fire", "a")]}
        self.assertFalse([p for p in check.problems(doc) if "не заполнено" in p["text"]])
        doc["nodes"][1]["data"] = {"variant": "stop"}
        texts = [p["text"] for p in check.problems(doc)]
        self.assertTrue(any(t.startswith("не заполнено") for t in texts), texts)

    def test_menu_shows_namespaces_in_order_and_hides_merged_actions(self):
        kinds = [k for k in nodes.catalog()["kinds"] if k["group"] == "action" and not k["hidden"]]
        labels = [k["label"] for k in kinds]
        self.assertLess(labels.index("Машина: Изменить статус"), labels.index("Экран: Показать"))
        self.assertNotIn("Изменить машину", labels)
        self.assertEqual(nodes.KINDS["act:account.access"].title, "variant")
