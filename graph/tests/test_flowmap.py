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


def by_id(flow):
    return {n["id"]: n for n in flow["nodes"]}


def edge(flow, src, to):
    return next((e for e in flow["edges"] if (e["src"], e["to"]) == (src, to)), None)


class FlowMapTests(TestCase):
    def graph(self):
        nodes = [node("go", "manual", name="Go"), stage("s1", "Door"), node("w", "wait", minutes=5), stage("s2", "Vault"),
                 node("a", "do:world_count", name="x"), node("n", "note")]
        wires = [wire("go", "fire", "s1"), wire("s1", "next", "a"), wire("a", "next", "w"), wire("w", "next", "s2")]
        return make(nodes, wires, slug="map")

    def test_nodes_are_starts_and_stages_and_the_rest_collapses_into_arrows(self):
        flow = flowmap.build(self.graph())
        found = by_id(flow)
        self.assertEqual({k: (v["role"], v["col"], v["state"]) for k, v in found.items()}, {"go": ("start", 0, "ahead"), "s1": ("stage", 1, "ahead"), "s2": ("stage", 2, "ahead")})
        self.assertEqual([(e["src"], e["to"], e["wait"]) for e in flow["edges"]], [("go", "s1", None), ("s1", "s2", None)])

    def test_waiting_is_written_on_the_arrow_and_marks_the_node_before(self):
        graph = self.graph()
        start_control(graph, "go")
        flow = flowmap.build(graph)
        found = by_id(flow)
        self.assertEqual((found["s1"]["state"], found["s1"]["hits"], found["s1"]["here"], found["s2"]["here"], found["s2"]["state"]), ("done", 1, True, False, "ahead"))
        wait = edge(flow, "s1", "s2")["wait"]
        self.assertEqual((wait["count"], wait["items"][0]["kind"], wait["waits"][0]["owner"]), (1, "time", ""))
        self.assertEqual((flow["here"], flowmap.here_titles(graph)), (1, ["Ждать 5 минут"]))

    def test_check_splits_into_labeled_arrows_on_separate_rows(self):
        graph = make([stage("s", "Start"), node("c", "check", condition="var:alarm"), stage("y", "Alarm"), stage("n", "Calm"), stage("z", "End")],
                     [wire("s", "next", "c"), wire("c", "yes", "y"), wire("c", "no", "n"), wire("y", "next", "z"), wire("n", "next", "z")], slug="lanes")
        flow = flowmap.build(graph)
        found = by_id(flow)
        self.assertEqual((edge(flow, "s", "y")["label"], edge(flow, "s", "n")["label"]), ("Истина", "Ложь"))
        self.assertEqual((found["y"]["col"], found["n"]["col"], found["z"]["col"]), (1, 1, 2))
        self.assertNotEqual(found["y"]["row"], found["n"]["row"])

    def test_several_starts_converge(self):
        graph = make([node("t1", "on:terminal.command", command="one"), node("t2", "on:terminal.command", command="two"), stage("s", "Meet")],
                     [wire("t1", "run", "s"), wire("t2", "run", "s")], slug="starts")
        flow = flowmap.build(graph)
        self.assertEqual(sorted((e["src"], e["to"]) for e in flow["edges"]), [("t1", "s"), ("t2", "s")])
        self.assertEqual(sorted(by_id(flow)[i]["title"] for i in ("t1", "t2")), ["one", "two"])
        self.assertEqual(by_id(flow)["t1"]["hint"], "Терминал: Введена команда · one")

    def test_waiting_at_the_dead_end_is_a_tail_of_the_last_node(self):
        graph = make([node("go", "manual", name="Go"), stage("s", "Last"), node("w", "wait", minutes=9)], [wire("go", "fire", "s"), wire("s", "next", "w")], slug="tail")
        start_control(graph, "go")
        flow = flowmap.build(graph)
        self.assertEqual([(t["node"], t["count"]) for t in flow["tails"]], [("s", 1)])
        self.assertTrue(by_id(flow)["s"]["here"])

    def test_without_stages_waits_and_events_become_nodes(self):
        graph = make([node("t", "on:terminal.command", command="go"), node("w", "wait", minutes=5)], [wire("t", "run", "w")], slug="plain")
        self.assertEqual(sorted(by_id(flowmap.build(graph))), ["t", "w"])

    def test_wait_carries_game_time_and_ids_for_the_author_actions(self):
        graph = self.graph()
        start_control(graph, "go")
        row = edge(flowmap.build(graph), "s1", "s2")["wait"]["waits"][0]
        self.assertRegex(row["until_game"], r"^\d{4}-\d\d-\d\d \d\d:\d\d$")
        self.assertTrue(row["id"] and row["run"])

    def test_a_loop_back_keeps_the_stages_in_story_order(self):
        graph = make([node("go", "manual", name="Go"), stage("s1", "One"), stage("s2", "Two"), stage("s3", "Three"), node("t", "on:terminal.command", command="retry"), stage("late", "Late")],
                     [wire("go", "fire", "s1"), wire("s1", "next", "s2"), wire("s2", "next", "s3"), wire("s3", "next", "late"), wire("late", "next", "t"), wire("t", "run", "s2")], slug="loopback")
        flow = flowmap.build(graph)
        found = by_id(flow)
        self.assertEqual([found[i]["col"] for i in ("s1", "s2", "s3", "late")], [1, 2, 3, 4])
        self.assertEqual([(e["src"], e["to"]) for e in flow["edges"] if e["back"]], [("late", "s2")])

    def test_empty_and_cycle_do_not_break(self):
        self.assertEqual(flowmap.build(make([], [], slug="empty"))["nodes"], [])
        graph = make([stage("a", "A"), stage("b", "B")], [wire("a", "next", "b"), wire("b", "next", "a")], slug="loop")
        flow = flowmap.build(graph)
        self.assertEqual(sorted(e["back"] for e in flow["edges"]), [False, True])
        self.assertEqual(flow["cols"], 2)


class ForkMapTests(BranchingBase):
    def test_fork_without_stages_gets_a_stub_lane_so_its_branches_can_be_opened(self):
        graph = self.graph(self.doc(repeat="yes", total=3, per=1, name="Red"))
        start_manual(graph, "m", self.boris)
        flow = flowmap.build(graph)
        stub = by_id(flow)["b#lane"]
        self.assertEqual((stub["role"], stub["branch"], stub["title"]), ("lane", "b", "В ветке нет этапов"))
        self.assertEqual(next(e for e in flow["edges"] if e["to"] == "b#lane")["wait"]["count"], 1)
        self.assertFalse(by_id(flow)["b"]["here"])                                              # свободная ветка не делает ветвление «стоящим»

    def test_branch_map_hangs_below_the_fork_with_a_count_on_the_waiting_arrow(self):
        inner = {"title": "Ветвление", "nodes": [node("h", "branch_head"), node("t1", "on:terminal.command", command="open"), node("own", "branch_owner", who="player"),
                                                 stage("si", "Вошла"), node("t2", "on:terminal.command", command="step"), stage("sd", "Дошла"), node("o", "branch_out")],
                 "wires": [wire("h", "next", "t1"), wire("t1", "run", "own"), wire("own", "next", "si"), wire("si", "next", "t2"), wire("t2", "run", "sd"), wire("sd", "next", "o")]}
        doc = {"nodes": [node("m", "manual"), node("b", "branching", group="g1", repeat="yes", total=3, per=1, name="Red")], "wires": [wire("m", "fire", "b")], "groups": {"g1": inner}}
        graph = self.graph(doc)
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "open")
        flow = flowmap.build(graph)
        found = by_id(flow)
        self.assertEqual((found["b"]["role"], found["b"]["title"], found["b"]["row"]), ("fork", "Red", 0))
        inner = [n for n in flow["nodes"] if n["branch"] == "b"]
        self.assertEqual(sorted(n["title"] for n in inner), ["Вошла", "Дошла"])
        self.assertTrue(all(n["row"] >= 1 for n in inner))                                  # дорожка ниже основной линии
        lane = next(e for e in flow["edges"] if e["src"] == "b" and e["lane"])
        self.assertEqual(lane["wait"]["count"], 1)                                          # свободная ветка ждёт «open»
        fork = flow["forks"][0]
        self.assertEqual((fork["title"], fork["repeat"], fork["taken"], fork["total"]), ("Red", True, 1, 3))
        self.assertEqual(sorted((b["state"], b["owner"]) for b in fork["branches"]), [("free", ""), ("taken", "ivan")])
        self.assertEqual(next(b for b in fork["branches"] if b["owner"] == "ivan")["at"], "step")


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
