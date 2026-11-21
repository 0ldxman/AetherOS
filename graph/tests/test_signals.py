"""Сигналы: «Послать сигнал» (куда: сценарий, ветка, мир; данные) и «Сигнал» (старт и ожидание: игрок, данные)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from graph.models import Run, Shared
from graph.runtime import start_manual
from graph.tests.test_branching import BranchingBase, rows
from graph.tests.test_runtime import make, node, wire
from graph.tests.test_variables import getv, setv


def count(name):
    return values.get(values.COUNT, "world", 0, name)


def send(i, name="go", scope="scenario", **extra):
    return node(i, "send_signal", name=name, scope=scope, **extra)


class SignalTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ivan, self.anna = users.create_user("ivan"), users.create_user("anna")

    def waiter(self, slug="waiter", **extra):
        """manual → ждёт сигнал «go» → счётчик c."""
        return make([node("m", "manual"), node("s", "signal", name="go", **extra), node("a", "do:world_count", name="c")],
                    [wire("m", "fire", "s"), wire("s", "got", "a")], slug=slug)

    def sender(self, slug="sender", **extra):
        return make([node("m", "manual"), send("x", **extra)], [wire("m", "fire", "x")], slug=slug)

    def test_world_wakes_other_scenarios_and_scenario_does_not(self):
        waiter = self.waiter()
        start_manual(waiter, "m", self.ivan)
        start_manual(self.sender(scope="scenario"), "m", self.anna)
        self.assertEqual(count("c"), 0)
        start_manual(self.sender("loud", scope="world"), "m", self.anna)
        self.assertEqual(count("c"), 1)

    def test_scenario_signal_wakes_other_flows_of_the_same_scenario(self):
        graph = make([node("m", "manual"), node("m2", "manual"), node("s", "signal", name="go"), node("a", "do:world_count", name="c"), send("x")],
                     [wire("m", "fire", "s"), wire("s", "got", "a"), wire("m2", "fire", "x")], slug="one")
        start_manual(graph, "m", self.ivan)
        self.assertEqual(count("c"), 0)
        start_manual(graph, "m2", self.anna)
        self.assertEqual(count("c"), 1)

    def test_branch_signal_stays_in_its_flow(self):
        """«Эта ветка»: слышит только ждущий этого же потока."""
        graph = make([node("m", "manual"), node("m2", "manual"), node("s", "signal", name="go"), node("a", "do:world_count", name="c"), send("x", scope="branch")],
                     [wire("m", "fire", "s"), wire("s", "got", "a"), wire("m2", "fire", "x")], slug="br")
        start_manual(graph, "m", self.ivan)
        start_manual(graph, "m2", self.ivan)
        self.assertEqual(count("c"), 0)

    def test_signal_starts_graph_by_scenario_or_world_only(self):
        make([node("s", "signal", name="go"), node("a", "do:world_count", name="c")], [wire("s", "got", "a")], slug="listen")
        start_manual(self.sender(scope="branch"), "m", self.ivan)
        start_manual(self.sender("other", scope="scenario"), "m", self.ivan)
        self.assertEqual(count("c"), 0)
        start_manual(self.sender("third", scope="world"), "m", self.ivan)
        self.assertEqual(count("c"), 1)

    def test_owned_flow_hears_signals_of_other_players(self):
        waiter = self.waiter()
        start_manual(waiter, "m", self.ivan)
        Run.objects.filter(graph=waiter).update(owner=self.ivan)
        start_manual(self.sender("loud", scope="world"), "m", self.anna)
        self.assertEqual(count("c"), 1)

    def test_payload_and_sender(self):
        """Данные идут вместе с сигналом, а «Игрок» — кто послал."""
        waiter = make([node("m", "manual"), node("s", "signal", name="go"), node("g", "data_get", rows=[{"id": "k1", "name": "color"}]),
                       node("a", "do:world_count", name="x"), node("b", "do:world_count", name="y")],
                      [wire("m", "fire", "s"), wire("s", "got", "a"), wire("a", "next", "b"), wire("g", "k1", "a", "f:name"), wire("s", "data", "g", "in"),
                       wire("s", "player", "b", "f:name")], slug="waiter")
        self.assertEqual([p for p in (waiter.doc or {}).get("nodes", []) if p["type"] == "signal"][0]["data"]["name"], "go")
        start_manual(waiter, "m", self.ivan)
        sender = make([node("m", "manual"), node("d", "dict", rows=rows(("color", "red"))), send("x", scope="world")],
                      [wire("m", "fire", "x"), wire("d", "value", "x", "f:payload")], slug="sender")
        start_manual(sender, "m", self.anna)
        self.assertEqual((count("red"), count("anna")), (1, 1))

    def test_data_defaults_to_flow_data(self):
        waiter = make([node("m", "manual"), node("s", "signal", name="go"), node("g", "data_get", rows=[{"id": "k1", "name": "color"}]),
                       node("a", "do:world_count", name="x")],
                      [wire("m", "fire", "s"), wire("s", "got", "a"), wire("g", "k1", "a", "f:name"), wire("s", "data", "g", "in")], slug="waiter")
        start_manual(waiter, "m", self.ivan)
        sender = make([node("m", "manual"), node("p", "data_set", rows=rows(("color", "blue"))), send("x", scope="world")],
                      [wire("m", "fire", "p"), wire("p", "next", "x")], slug="sender")
        start_manual(sender, "m", self.anna)
        self.assertEqual(count("blue"), 1)

    def test_wait_fields_skipped_for_signal(self):
        from graph import nodes as N

        self.assertEqual(N.KINDS["signal"].wait_skip, ("past", "own"))


def safe_doc():
    """Сценарий «Сейф»: три игрока, каждый в своей ветке вводит «unlock» и шлёт сигнал; основной поток считает ключи в переменных сценария
    и по третьему открывает сейф. Ветки — «Ветвление» с повтором (по одной на игрока), сигнал несёт данные, «Игрок» — кто ввёл."""
    inner = [node("h", "branch_head"), node("t", "on:terminal.command", command="unlock"), node("d", "dict", rows=rows(("way", "terminal"))),
             node("own", "branch_owner", who="player"), send("x", name="key", scope="scenario"), node("o", "branch_out")]
    inner_wires = [wire("h", "next", "t"), wire("t", "run", "own"), wire("own", "next", "x"), wire("d", "value", "x", "f:payload"), wire("x", "next", "o")]
    nodes = [node("m", "manual"), node("b", "branching", group="g1", name="Keys", repeat="yes", total=3, per=1),
             node("sig", "signal", name="key"), node("way", "data_get", rows=[{"id": "k1", "name": "way"}]),
             setv("count", ("keys", "1"), mode="op"), setv("who", ("who", None), mode="op", op="push"), setv("last", ("last_way", None)),
             getv("have", "keys"), node("enough", "compare", op="ge", b="3"), node("chk", "check"), node("open", "do:world_count", name="safe-open")]
    nodes[5]["data"]["rows"] = [{"id": "k1", "name": "who"}]
    nodes[6]["data"]["rows"] = [{"id": "k1", "name": "last_way"}]
    wires = [wire("m", "fire", "b"), wire("b", "next", "sig"), wire("sig", "got", "count"), wire("count", "next", "who"), wire("who", "next", "last"),
             wire("last", "next", "chk"), wire("sig", "player", "who", "f:k1"), wire("sig", "data", "way", "in"), wire("way", "k1", "last", "f:k1"),
             wire("have", "k1", "enough", "f:a"), wire("enough", "value", "chk", "f:condition"), wire("chk", "yes", "open"), wire("chk", "no", "sig")]
    return {"nodes": nodes, "wires": wires, "groups": {"g1": {"title": "Keys", "nodes": inner, "wires": inner_wires}}}


class SafeScenarioTests(BranchingBase):
    def test_three_players_open_the_safe(self):
        graph = self.graph(safe_doc(), slug="safe")
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "unlock")
        self.cmd(self.anna, "unlock")
        self.assertEqual(count("safe-open"), 0)
        self.cmd(self.boris, "unlock")
        self.assertEqual(count("safe-open"), 1)
        self.assertEqual(Shared.objects.get(graph=graph).data, {"keys": 3, "who": ["ivan", "anna", "boris"], "last_way": "terminal"})

    def test_one_player_cannot_take_two_keys(self):
        graph = self.graph(safe_doc(), slug="safe")
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "unlock")
        self.cmd(self.ivan, "unlock")
        self.assertEqual(Shared.objects.get(graph=graph).data["keys"], 1)


class MergeTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ivan, self.anna = users.create_user("ivan"), users.create_user("anna")

    def test_merge_signal_data_into_flow_data(self):
        """«Слить»: данные из сигнала переходят в данные потока получателя (в том числе вложенные)."""
        waiter = make([node("m", "manual"), node("s", "signal", name="go"), node("g", "data_set", mode="merge"), node("r", "data_get", rows=[{"id": "k1", "name": "team.color"}]),
                       node("a", "do:world_count", name="x")],
                      [wire("m", "fire", "s"), wire("s", "got", "g"), wire("s", "data", "g", "f:source"), wire("g", "next", "a"), wire("r", "k1", "a", "f:name")], slug="waiter")
        start_manual(waiter, "m", self.ivan)
        sender = make([node("m", "manual"), node("d", "dict", rows=rows(("team.color", "red"), ("team.size", "3"))), send("x", scope="world")],
                      [wire("m", "fire", "x"), wire("d", "value", "x", "f:payload")], slug="sender")
        start_manual(sender, "m", self.anna)
        self.assertEqual(count("red"), 1)
        self.assertEqual(Run.objects.get(graph=waiter).state["data"], {"team": {"color": "red", "size": "3"}})
