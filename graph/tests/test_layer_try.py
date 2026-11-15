"""Попытка снять слой: граф у слоя объекта (или «любой слой»), нода «Слой объекта»."""
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from engine import values
from filesystem.testing import make_app, make_file
from graph import owned, runtime
from graph.models import Graph
from graph.runtime import Doc, value_of
from machines.models import Machine, MachineProfile
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class LayerAttemptTests(TerminalClient, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", icon="terminal", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1)
        cls.vault = make_file(cls.main, "/home/vault.dat", state="> encrypted hunter2\n> encrypted opensesame").item

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def inner(self, key, answer, exits=None):
        graph = owned.ensure("layer", key)
        nodes = [{"id": "s", "type": "attempt:layer", "x": 0, "y": 0, "data": {}},
                 {"id": "a", "type": "answer", "x": 0, "y": 0, "data": answer}]
        wires = [{"from": "s", "out": "go", "to": "a", "in": "in"}]
        if exits:
            nodes.append({"id": "o", "type": "group_out", "x": 0, "y": 0,
                          "data": {"sockets": [{"name": name, "label": name, "type": "event"} for name in exits.values()]}})
            wires += [{"from": "a", "out": out, "to": "o", "in": name} for out, name in exits.items()]
        graph.doc = {"nodes": nodes, "wires": wires}
        graph.save()
        runtime.rebuild_starts(graph)
        return graph

    def test_allow_removes_without_the_password_and_deny_says_why(self):
        self.inner(f"{self.vault.slug}#1", {"mode": "allow"})
        self.inner(f"{self.vault.slug}#2", {"mode": "deny", "text": "the second lock holds"})
        self.assertEqual(self.run_command("ward /home/vault.dat whatever")["exit_code"], 0)
        refused = self.run_command("ward /home/vault.dat opensesame")
        self.assertEqual(refused["exit_code"], 1)
        self.assertIn("the second lock holds", refused["output"])

    def test_any_layer_graph_answers_when_there_is_no_own(self):
        self.inner(f"{self.vault.slug}#*", {"mode": "deny", "text": "sealed"})
        self.assertIn("sealed", self.run_command("ward /home/vault.dat hunter2")["output"])

    def test_as_usual_reports_the_outcome_to_scenarios(self):
        self.inner(f"{self.vault.slug}#*", {"mode": "default"}, {"allowed": "off", "refused": "wrong"})
        story = Graph.objects.create(slug="story", title="story", active=True, doc={
            "nodes": [{"id": "l", "type": "ent:layer", "x": 0, "y": 0, "data": {"mode": "current", "item": self.vault.slug}},
                      {"id": "t", "type": "try:layer", "x": 0, "y": 0, "data": {"repeat": "always"}},
                      {"id": "off", "type": "do:world_count", "x": 0, "y": 0, "data": {"name": "off"}},
                      {"id": "wrong", "type": "do:world_count", "x": 0, "y": 0, "data": {"name": "wrong"}}],
            "wires": [{"from": "l", "out": "value", "to": "t", "in": "f:layer"}, {"from": "t", "out": "off", "to": "off", "in": "in"},
                      {"from": "t", "out": "wrong", "to": "wrong", "in": "in"}]})
        runtime.rebuild_starts(story)
        self.run_command("ward /home/vault.dat nope")
        self.run_command("ward /home/vault.dat hunter2")
        self.assertEqual((values.get("count", "world", 0, "off"), values.get("count", "world", 0, "wrong")), (1, 1))

    def test_layer_node_modes_and_progress(self):
        run = SimpleNamespace(user=self.user, state={})

        def get(out, **data):
            doc = Doc({"nodes": [{"id": "l", "type": "ent:layer", "data": {"item": self.vault.slug, **data}}]})
            return value_of(run, doc, "l", out)

        self.assertEqual(get("value", mode="last"), f"{self.vault.slug}#2")
        self.assertEqual(get("value", mode="type", kind="encrypted"), f"{self.vault.slug}#1")
        self.assertEqual(get("value", mode="number", number=5), "")
        self.assertEqual((get("number"), get("left")), (1, 2))
        self.run_command("ward /home/vault.dat hunter2")
        self.assertEqual((get("number"), get("left"), get("removed", mode="top")), (2, 1, True))
