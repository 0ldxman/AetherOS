"""«Для каждого» группой: ветка на элемент, «Конец ветки», режимы Все / Первого / N, «Ждать от: Элемента»."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from graph import check, upgrade
from graph.models import Run, Wait
from graph.runtime import start_manual
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile


def box(list_, mode="all", need=None, inner=None, inner_wires=None):
    """Сценарий: вручную → «Для каждого» (группа g1) → «Готово» — счётчик мира done."""
    data = {"group": "g1", "list": list_, "mode": mode, **({"need": need} if need else {})}
    inner = inner or [node("s", "branch_in"), node("o", "branch_out")]
    doc_wires = inner_wires if inner_wires is not None else [wire("s", "next", "o")]
    return {"nodes": [node("m", "manual"), node("e", "each", **data), node("d", "do:world_count", name="done")],
            "wires": [wire("m", "fire", "e"), wire("e", "done", "d")],
            "groups": {"g1": {"title": "Для каждого", "nodes": inner, "wires": doc_wires}}}


def done():
    return values.get(values.COUNT, "world", 0, "done")


class EachTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ivan, self.anna = users.create_user("ivan"), users.create_user("anna")
        self.core = Machine.objects.create(name="Core", hostname="core")
        for login in ("a1", "a2", "a3"):
            MachineProfile.objects.create(machine=self.core, login=login)

    def graph(self, doc, slug):
        graph = make(doc["nodes"], doc["wires"], slug=slug)
        graph.doc = doc
        graph.save()
        return graph

    def test_branches_return_at_once(self):
        graph = self.graph(box(["a1@core", "a2@core"]), "sync")
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        start_manual(graph, "m", self.ivan)
        self.assertEqual(done(), 1)

    def test_all_waits_every_account(self):
        inner = [node("s", "branch_in"), node("w", "on:terminal.command", command="go", own="item"), node("o", "branch_out")]
        graph = self.graph(box(["a1@core", "a2@core"], inner=inner, inner_wires=[wire("s", "next", "w"), wire("w", "run", "o")]), "all")
        start_manual(graph, "m", self.ivan)
        self.assertEqual((done(), Run.objects.filter(parent__isnull=False, status="running").count()), (0, 2))
        emit("command.run", self.anna, machine="core", login="a3", command="go")      # не та учётка — никого
        emit("command.run", self.anna, machine="core", login="a1", command="go")
        self.assertEqual(done(), 0)
        emit("command.run", self.ivan, machine="core", login="a2", command="go")
        self.assertEqual(done(), 1)
        parent = Run.objects.get(parent__isnull=True)
        self.assertEqual(parent.status, "done")
        self.assertEqual(parent.state["vals"]["e"], {"finished": ["a1@core", "a2@core"], "first": "a1@core"})

    def test_first_cancels_the_rest(self):
        inner = [node("s", "branch_in"), node("w", "on:terminal.command", command="go", own="item"), node("o", "branch_out")]
        graph = self.graph(box(["ivan", "anna"], mode="first", inner=inner, inner_wires=[wire("s", "next", "w"), wire("w", "run", "o")]), "first")
        start_manual(graph, "m")
        emit("command.run", self.anna, machine="core", login="a1", command="go")
        self.assertEqual(done(), 1)
        self.assertFalse(Wait.objects.exists())
        self.assertEqual(Run.objects.filter(status="running").count(), 0)
        self.assertEqual(Run.objects.get(parent__isnull=True).state["vals"]["e"]["first"], "anna")

    def test_player_element_is_the_initiator(self):
        inner = [node("s", "branch_in"), node("t", "act:tag", variant="on", owner="player", name="seen"), node("o", "branch_out")]
        graph = self.graph(box(["ivan", "anna"], inner=inner, inner_wires=[wire("s", "next", "t"), wire("t", "next", "o")]), "init")
        start_manual(graph, "m")
        self.assertTrue(values.on("player", self.ivan.pk, "seen") and values.on("player", self.anna.pk, "seen"))
        self.assertEqual(done(), 1)

    def test_n_of_them(self):
        inner = [node("s", "branch_in"), node("w", "on:terminal.command", command="go", own="item"), node("o", "branch_out")]
        graph = self.graph(box(["a1@core", "a2@core", "a3@core"], mode="count", need=2, inner=inner,
                               inner_wires=[wire("s", "next", "w"), wire("w", "run", "o")]), "n")
        start_manual(graph, "m")
        emit("command.run", self.anna, machine="core", login="a3", command="go")
        self.assertEqual(done(), 0)
        emit("command.run", self.anna, machine="core", login="a1", command="go")
        self.assertEqual(done(), 1)
        self.assertEqual(Run.objects.filter(status="running").count(), 0)

    def test_old_foreach_without_branches_becomes_a_box(self):
        doc = {"nodes": [node("f", "foreach")], "wires": []}
        self.assertTrue(upgrade.each_boxes(doc))
        self.assertEqual(doc["nodes"][0]["type"], "each")
        inner = doc["groups"][doc["nodes"][0]["data"]["group"]]
        self.assertEqual([n["type"] for n in inner["nodes"]], ["branch_in", "branch_out"])
        self.assertFalse(upgrade.each_boxes(doc))
