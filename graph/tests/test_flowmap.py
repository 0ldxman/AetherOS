"""Карта сценария и журнал: опорные ноды, колонки, где сценарий стоит сейчас, ветвления, записи журнала."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from graph import flowmap, journal
from graph.models import Entry
from graph.runtime import reset_scenario, start_control, start_manual
from graph.tests.test_branching import BranchingBase
from graph.tests.test_runtime import make, node, wire


def stage(i, title):
    return node(i, "stage", title=title)


class FlowMapTests(TestCase):
    def graph(self):
        nodes = [node("go", "manual", name="Go"), stage("s1", "Door"), node("w", "wait", minutes=5), stage("s2", "Vault"),
                 node("a", "do:world_count", name="x"), node("n", "note")]
        wires = [wire("go", "fire", "s1"), wire("s1", "next", "a"), wire("a", "next", "w"), wire("w", "next", "s2")]
        return make(nodes, wires, slug="map")

    def by_id(self, flow):
        return {n["id"]: n for n in flow["nodes"]}

    def test_milestones_columns_and_edges(self):
        flow = flowmap.build(self.graph())
        found = self.by_id(flow)
        self.assertEqual(set(found), {"s1", "w", "s2"})                       # кнопка пульта, действие и заметка — не опорные
        self.assertEqual([found[i]["col"] for i in ("s1", "w", "s2")], [0, 1, 2])
        self.assertEqual([(e["from"], e["to"]) for e in flow["edges"]], [("s1", "w"), ("w", "s2")])    # действие между ними схлопнулось
        self.assertTrue(all(n["state"] == "ahead" for n in flow["nodes"]))

    def test_progress_is_shared_and_shows_where_it_waits(self):
        graph = self.graph()
        start_control(graph, "go")
        found = self.by_id(flowmap.build(graph))
        self.assertEqual((found["s1"]["state"], found["s1"]["hits"], found["w"]["state"], found["w"]["here"], found["s2"]["state"]), ("done", 1, "here", 1, "ahead"))
        self.assertEqual(found["w"]["waits"][0]["kind"], "time")
        self.assertEqual(flowmap.here_titles(graph), [found["w"]["title"]])

    def test_empty_and_cycle_do_not_break(self):
        self.assertEqual(flowmap.build(make([], [], slug="empty")), {"nodes": [], "edges": [], "cols": 0, "rows": 0, "forks": []})
        graph = make([stage("a", "A"), stage("b", "B")], [wire("a", "next", "b"), wire("b", "next", "a")], slug="loop")
        flow = flowmap.build(graph)
        self.assertEqual([e["back"] for e in flow["edges"]].count(True), 1)
        self.assertEqual(flow["cols"], 2)


class ForkMapTests(BranchingBase):
    def test_fork_lists_branches_and_owner(self):
        graph = self.graph(self.doc(repeat="yes", total=3, per=1, name="Red"))
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "open")
        flow = flowmap.build(graph)
        fork = flow["forks"][0]
        self.assertEqual((fork["title"], fork["repeat"], fork["taken"], fork["total"]), ("Red", True, 1, 3))
        self.assertEqual(sorted(b["state"] for b in fork["branches"]), ["free", "taken"])
        self.assertTrue(any(n["branch"] == "b" for n in flow["nodes"]))        # ноды внутри ветвления помечены его id
        self.assertTrue(any(e["from"] == "b" and e["to"] == "b/h" for e in flow["edges"]))


class JournalTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_stage_start_control_and_reset_are_recorded(self):
        graph = make([node("t", "ctl_switch", name="Alarm"), stage("s", "Door"), node("m", "on:tag", owner="player", name="met"), stage("s2", "Met")],
                     [wire("t", "on", "s"), wire("m", "set", "s2")], slug="log")
        start_control(graph, "t", True, user=None, author=get_user_model().objects.create_user("boss", is_staff=True))
        kinds = [(e.kind, e.who) for e in Entry.objects.filter(graph=graph).order_by("id")]
        self.assertEqual(kinds, [("control", "boss"), ("stage", "")])
        self.assertEqual(Entry.objects.get(kind="control").text, "Управление «Alarm» = вкл")
        reset_scenario(graph)
        self.assertEqual(Entry.objects.filter(graph=graph).count(), 2)       # сброс стирает потоки, но не журнал

    def test_page_goes_from_new_to_old(self):
        graph = make([], [], slug="pg")
        for i in range(5):
            journal.note(graph, "stage", f"e{i}")
        rows, more = journal.page(graph, limit=2)
        self.assertEqual(([r.text for r in rows], more), (["e4", "e3"], rows[-1].pk))
        rows, more = journal.page(graph, before=more, limit=10)
        self.assertEqual(([r.text for r in rows], more), (["e2", "e1", "e0"], None))
        self.assertEqual([r.text for r in journal.page(graph, kind="start")[0]], [])

    def test_prune_keeps_the_newest(self):
        graph = make([], [], slug="pr")
        for i in range(8):
            journal.note(graph, "stage", f"e{i}")
        journal.prune(graph, keep=3)
        self.assertEqual([e.text for e in Entry.objects.filter(graph=graph)], ["e7", "e6", "e5"])
