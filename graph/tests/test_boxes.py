"""Группы, сценарий как нода, запуск другого сценария, сигналы."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from graph import check, runtime
from graph.models import Graph, Run
from graph.tests.test_runtime import counter, make, node, wire


def gin(node_id, *names):
    return node(node_id, "group_in", sockets=[{"name": n, "label": n} for n in names])


def gout(node_id, *names):
    return node(node_id, "group_out", sockets=[{"name": n, "label": n} for n in names])


class GroupTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def doc_with_group(self):
        group = {"title": "G", "nodes": [gin("i", "s1"), node("a", "do:world_count", name="c"), gout("o", "done")],
                 "wires": [wire("i", "s1", "a"), wire("a", "next", "o", "done")]}
        return {"nodes": [node("m", "manual"), node("g", "group", group="grp"), node("b", "do:world_count", name="d")],
                "wires": [wire("m", "fire", "g", "s1"), wire("g", "done", "b")], "groups": {"grp": group}}

    def test_group_runs_inner_nodes_and_passes_out(self):
        doc = self.doc_with_group()
        graph = Graph.objects.create(slug="g", title="g", active=True, doc=doc)
        runtime.rebuild_starts(graph)
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual((counter("c"), counter("d")), (1, 1))
        self.assertTrue(graph.hits.filter(node="g/a").exists())
        self.assertEqual(check.problems(doc, "g"), [])

    def test_noun_inside_group_is_a_start(self):
        group = {"nodes": [node("f", "flag", name="x"), node("a", "do:world_count", name="c")], "wires": [wire("f", "set", "a")]}
        graph = Graph.objects.create(slug="g", title="g", active=True, doc={"nodes": [node("g", "group", group="grp")], "wires": [], "groups": {"grp": group}})
        runtime.rebuild_starts(graph)
        from engine.events import emit

        emit("flag.set", self.ivan, flag="x")
        self.assertEqual(counter("c"), 1)

    def test_checks(self):
        doc = self.doc_with_group()
        doc["nodes"].append(node("x", "group", group="nope"))
        doc["wires"].append(wire("m", "fire", "g", "bad"))
        doc["groups"]["grp"]["nodes"][1]["data"] = {}
        found = [(p["node"], p["text"]) for p in check.problems(doc, "g")]
        self.assertIn(("x", "нет определения группы"), found)
        self.assertIn(("g", "нет входа «bad»"), found)
        self.assertIn(("grp::a", "не заполнено «Счётчик»"), found)

    def test_clean_keeps_groups(self):
        cleaned = check.clean(self.doc_with_group())
        self.assertEqual(set(cleaned["groups"]["grp"]), {"title", "nodes", "wires"})


class ScenarioNodeTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.inner = make([gin("i", "go"), node("a", "do:world_count", name="c"), gout("o", "done"),
                           node("f", "flag", name="x"), node("z", "do:world_count", name="own")],
                          [wire("i", "go", "a"), wire("a", "next", "o", "done"), wire("f", "set", "z")], slug="inner")

    def test_scenario_node_inlines_other_graph(self):
        outer = make([node("m", "manual"), node("s", "scenario", graph="inner"), node("b", "do:world_count", name="d")],
                     [wire("m", "fire", "s", "go"), wire("s", "done", "b")], slug="outer")
        runtime.start_manual(outer, "m", self.ivan)
        self.assertEqual((counter("c"), counter("d")), (1, 1))
        self.assertFalse(Run.objects.filter(graph=self.inner).exists())
        self.assertNotIn("s/f", [row.node for row in outer.starts.all()])           # старты вложенного сценария не наследуются

    def test_cache_follows_changes_of_inner_graph(self):
        outer = make([node("m", "manual"), node("s", "scenario", graph="inner")], [wire("m", "fire", "s", "go")], slug="outer")
        runtime.doc_of(outer)
        doc = self.inner.doc
        doc["nodes"][1]["data"]["name"] = "e"
        self.inner.doc = doc
        self.inner.save()
        runtime.start_manual(outer, "m", self.ivan)
        self.assertEqual((counter("c"), counter("e")), (0, 1))

    def test_self_include_is_reported(self):
        doc = {"nodes": [node("s", "scenario", graph="inner")], "wires": []}
        self.assertTrue(any("сам себя" in p["text"] for p in check.problems(doc, "inner")))

    def test_launch_starts_other_graph_for_same_player(self):
        outer = make([node("m", "manual"), node("l", "launch", graph="inner"), node("b", "do:world_count", name="d")],
                     [wire("m", "fire", "l"), wire("l", "next", "b")], slug="outer")
        runtime.start_manual(outer, "m", self.ivan)
        self.assertEqual((counter("c"), counter("d")), (1, 1))
        self.assertEqual(Run.objects.get(graph=self.inner).user, self.ivan)

    def test_launch_of_inactive_fails(self):
        Graph.objects.filter(pk=self.inner.pk).update(active=False)
        outer = make([node("m", "manual"), node("l", "launch", graph="inner"), node("b", "do:world_count", name="d")],
                     [wire("m", "fire", "l"), wire("l", "fail", "b")], slug="outer")
        runtime.start_manual(outer, "m", self.ivan)
        self.assertEqual(counter("d"), 1)


class SignalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")

    def test_signal_to_player_and_to_all(self):
        waiter = make([node("m", "manual"), node("s", "signal", name="go"), node("a", "do:world_count", name="c")],
                      [wire("m", "fire", "s"), wire("s", "got", "a")], slug="waiter")
        sender = make([node("m", "manual"), node("x", "send_signal", name="go", to="player")], [wire("m", "fire", "x")], slug="sender")
        for user in (self.ivan, self.anna):
            runtime.start_manual(waiter, "m", user)
        runtime.start_manual(sender, "m", self.ivan)
        self.assertEqual(counter("c"), 1)                                    # только ivan
        loud = make([node("m", "manual"), node("x", "send_signal", name="go", to="all")], [wire("m", "fire", "x")], slug="loud")
        runtime.start_manual(loud, "m")
        self.assertEqual(counter("c"), 2)

    def test_signal_starts_graph(self):
        make([node("s", "signal", name="go"), node("a", "do:world_count", name="c")], [wire("s", "got", "a")], slug="listen")
        sender = make([node("m", "manual"), node("x", "send_signal", name="go")], [wire("m", "fire", "x")], slug="sender")
        runtime.start_manual(sender, "m", self.ivan)
        self.assertEqual(counter("c"), 1)
