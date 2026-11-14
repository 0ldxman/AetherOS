"""Граф перекрывает хуки слоя файла («Вместо хуков слоя»)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from graph import runtime
from graph.tests.test_runtime import make, node, wire


class OverrideTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_start_with_override_claims_the_event(self):
        make([node("f", "file", path="/home/*", override=True), node("a", "do:world_count", name="c")], [wire("f", "layer_failed", "a")])
        self.assertTrue(runtime.overrides("layer.failed", self.ivan, path="/home/door.bin", layer="password"))
        self.assertFalse(runtime.overrides("layer.failed", self.ivan, path="/srv/door.bin"))
        self.assertFalse(runtime.overrides("layer.removed", self.ivan, path="/home/door.bin"))

    def test_without_override_hooks_stay(self):
        make([node("f", "file", path="/home/*"), node("a", "do:world_count", name="c")], [wire("f", "layer_failed", "a")])
        self.assertFalse(runtime.overrides("layer.failed", self.ivan, path="/home/door.bin"))

    def test_waiting_node_overrides_only_for_its_player(self):
        graph = make([node("m", "manual"), node("f", "file", path="/home/*", override=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "read", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        other = get_user_model().objects.create_user("anna")
        self.assertTrue(runtime.overrides("file.read", self.ivan, path="/home/x"))
        self.assertFalse(runtime.overrides("file.read", other, path="/home/x"))

    def test_answer_outside_an_attempt_is_logged(self):
        from world.models import WorldEvent

        graph = make([node("m", "manual"), node("a", "answer", mode="allow")], [wire("m", "fire", "a")])
        runtime.start_manual(graph, "m")
        self.assertTrue(WorldEvent.objects.filter(text__contains="без попытки").exists())


class AttemptCheckTests(TestCase):
    def test_attempt_without_instant_answer_is_warned(self):
        from graph import check

        bad = {"nodes": [node("m", "machine", host="x"), node("w", "wait", minutes=1), node("a", "answer")],
               "wires": [wire("m", "attempt", "w"), wire("w", "next", "a")]}
        self.assertTrue(any("мгновенного" in p["text"] for p in check.problems(bad)))
        good = {"nodes": [node("m", "machine", host="x"), node("c", "check", condition="tag:x"), node("a", "answer")],
                "wires": [wire("m", "attempt", "c"), wire("c", "yes", "a")]}
        self.assertFalse(any("мгновенного" in p["text"] for p in check.problems(good)))
