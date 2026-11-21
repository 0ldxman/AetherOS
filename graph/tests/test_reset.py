"""«Сценарий: Начать заново» и «Ветка: Начать заново»."""
from graph.models import Branching, Run, Shared
from graph.runtime import start_manual
from graph.tests.test_branching import BranchingBase, count, counter
from graph.tests.test_runtime import node, wire
from graph.tests.test_variables import setv


class ScenarioResetTests(BranchingBase):
    def doc(self, condition="var:keys>=1", **reset):
        """«go» (старт игрока, один раз за игру) прибавляет keys; кнопка «again» сбрасывает по условию; после сброса / мимо — счётчики."""
        return {"nodes": [node("t", "on:terminal.command", command="go"), setv("s", ("keys", "1"), mode="op"), node("b", "manual"),
                          node("r", "scenario_reset", condition=condition, **reset), counter("after", "after")],
                "wires": [wire("t", "run", "s"), wire("b", "fire", "r"), wire("r", "next", "after")]}

    def test_start_fires_again_after_reset(self):
        graph = self.graph(self.doc())
        self.assertEqual(self.errors(graph), [])
        self.cmd(self.ivan, "go")
        self.cmd(self.anna, "go")                                         # один раз за игру: второй не стартует
        self.assertEqual(Shared.objects.get(graph=graph).data, {"keys": 1})
        start_manual(graph, "b", self.boris)                              # условие верно: сброс, «Поток» не идёт
        self.assertEqual(count("after"), 0)
        self.assertFalse(Shared.objects.filter(graph=graph).exists())
        self.cmd(self.anna, "go")
        self.assertEqual(Shared.objects.get(graph=graph).data, {"keys": 1})

    def test_false_condition_passes_through(self):
        graph = self.graph(self.doc(condition="var:keys>=5"))
        self.cmd(self.ivan, "go")
        start_manual(graph, "b", self.boris)
        self.assertEqual(count("after"), 1)
        self.assertEqual(Shared.objects.get(graph=graph).data, {"keys": 1})

    def test_keep_variables(self):
        graph = self.graph(self.doc(condition="", keep_vars=True))
        self.cmd(self.ivan, "go")
        start_manual(graph, "b", self.boris)
        self.assertEqual(Shared.objects.get(graph=graph).data, {"keys": 1})
        self.assertEqual(Run.objects.filter(graph=graph).count(), 0)

    def test_branchings_and_turns_are_cleared(self):
        doc = self.doc(condition="")
        doc["nodes"] += [node("m", "manual"), node("br", "branching", group="g1", repeat="yes", total=2, per=1), node("tn", "turns", count=2),
                         counter("one", "one"), counter("two", "two")]
        doc["wires"] += [wire("m", "fire", "br"), wire("br", "next", "tn"), wire("tn", "b1", "one"), wire("tn", "b2", "two")]
        doc["groups"] = {"g1": {"title": "x", "nodes": [node("h", "branch_head"), node("t1", "on:terminal.command", command="open"), node("o", "branch_out")],
                                "wires": [wire("h", "next", "t1"), wire("t1", "run", "o")]}}
        graph = self.graph(doc)
        start_manual(graph, "m", self.boris)
        self.assertTrue(Branching.objects.filter(graph=graph).exists())
        start_manual(graph, "b", self.boris)
        self.assertFalse(Branching.objects.filter(graph=graph).exists())
        self.assertFalse(Run.objects.filter(graph=graph).exists())
        start_manual(graph, "m", self.boris)                                # счёт «По очереди» начался с первой ветки: one, не two
        self.assertEqual((count("one"), count("two")), (2, 0))


class BranchRestartTests(BranchingBase):
    def doc(self, repeat="yes", condition=""):
        inner = [node("h", "branch_head"), node("t1", "on:terminal.command", command="open"), node("own", "branch_owner", who="player"),
                 node("t2", "on:terminal.command", command="retry"), node("rs", "branch_restart", condition=condition), counter("ok", "ok"), node("o", "branch_out")]
        wires = [wire("h", "next", "t1"), wire("t1", "run", "own"), wire("own", "next", "t2"), wire("t2", "run", "rs"), wire("rs", "next", "ok"), wire("ok", "next", "o")]
        return {"nodes": [node("m", "manual"), node("b", "branching", group="g1", repeat=repeat, total=3, per=1)], "wires": [wire("m", "fire", "b")],
                "groups": {"g1": {"title": "x", "nodes": inner, "wires": wires}}}

    def spawn(self, graph):
        return Branching.objects.get(graph=graph, node="b")

    def test_restart_returns_the_place(self):
        graph = self.graph(self.doc())
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "open")
        self.assertEqual((self.spawn(graph).taken, self.spawn(graph).users), (1, {str(self.ivan.pk): 1}))
        self.cmd(self.ivan, "retry")                                        # без условия — ветка начинается заново
        self.assertEqual((self.spawn(graph).taken, self.spawn(graph).users), (0, {str(self.ivan.pk): 0}))
        self.assertEqual(count("ok"), 0)
        self.assertEqual(Run.objects.filter(graph=graph, outcome="restarted").count(), 1)
        self.cmd(self.ivan, "open")                                          # игрок снова может занять ветку (на инициатора 1)
        self.assertEqual(self.spawn(graph).taken, 1)

    def test_false_condition_keeps_the_branch(self):
        graph = self.graph(self.doc(condition="var:never"))
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "open")
        self.cmd(self.ivan, "retry")
        self.assertEqual((self.spawn(graph).taken, count("ok")), (1, 1))

    def test_without_repeat_a_fresh_branch_appears(self):
        graph = self.graph(self.doc(repeat="no"))
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "open")
        self.cmd(self.ivan, "retry")
        branches = Run.objects.filter(graph=graph, status=Run.Status.RUNNING, state__fork="b")
        self.assertEqual(branches.count(), 1)
        self.assertEqual(Run.objects.filter(graph=graph, outcome="restarted").count(), 1)
