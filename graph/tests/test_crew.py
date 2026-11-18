"""Группы инициаторов и «Занять тег»."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from graph import check, crews
from graph.models import Crew
from graph.runtime import start_manual
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile


def count(name):
    return values.get(values.COUNT, "world", 0, name)


def counter(i, name):
    return node(i, "do:world_count", name=name)


class CrewBase(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ivan, self.anna, self.boris = users.create_user("ivan"), users.create_user("anna"), users.create_user("boris")
        core = Machine.objects.create(name="Core", hostname="core")
        MachineProfile.objects.create(machine=core, login="root")

    def graph(self, doc, slug="crew"):
        graph = make(doc["nodes"], doc["wires"], slug=slug)
        graph.doc = doc
        graph.save()
        return graph

    def go(self, user, command="go"):
        emit("command.run", user, machine="core", login="root", command=command)

    def errors(self, graph):
        return [p for p in check.problems(graph.doc) if p["level"] == "error"]


class CrewNodeTests(CrewBase):
    def doc(self, **extra):
        return {"nodes": [node("m", "manual"), node("c", "crew", name="red", **extra), counter("in", "in"), counter("full", "full")],
                "wires": [wire("m", "fire", "c"), wire("c", "next", "in"), wire("c", "full", "full")]}

    def test_add_with_limit_closes_when_full(self):
        graph = self.graph(self.doc(mode="add", limit=2))
        self.assertEqual(self.errors(graph), [])
        for user in (self.ivan, self.anna, self.boris):
            start_manual(graph, "m", user)
        self.assertEqual((count("in"), count("full")), (2, 1))
        self.assertEqual(crews.members(graph, "red"), ["ivan", "anna"])
        self.assertTrue(Crew.objects.get(name="red").closed)

    def test_already_member_is_not_full(self):
        graph = self.graph(self.doc(mode="add", limit=1))
        start_manual(graph, "m", self.ivan)
        start_manual(graph, "m", self.ivan)
        self.assertEqual((count("in"), count("full")), (2, 0))

    def test_close_open_remove(self):
        graph = self.graph(self.doc(mode="add"))
        start_manual(graph, "m", self.ivan)
        crews.set_closed(graph, "red", True)
        start_manual(graph, "m", self.anna)
        self.assertEqual((count("in"), count("full")), (1, 1))
        crews.set_closed(graph, "red", False)
        crews.leave(graph, "red", self.ivan)
        start_manual(graph, "m", self.anna)
        self.assertEqual(crews.members(graph, "red"), ["anna"])


class ClaimTests(CrewBase):
    def test_first_takes_second_is_late(self):
        doc = {"nodes": [node("m", "manual"), node("c", "claim", scope="world", name="winner"), counter("s", "set"), counter("a", "already")],
               "wires": [wire("m", "fire", "c"), wire("c", "set", "s"), wire("c", "already", "a")]}
        graph = self.graph(doc)
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.ivan)
        start_manual(graph, "m", self.anna)
        self.assertEqual((count("set"), count("already")), (1, 1))
