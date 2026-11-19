"""«Ветвление»: ветка, вакансия с повтором, владелец ветки, набор (закрыть и открыть)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from graph import check, crews
from graph.models import Branching, Run
from graph.runtime import start_manual
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile


def count(name):
    return values.get(values.COUNT, "world", 0, name)


def counter(i, name):
    return node(i, "do:world_count", name=name)


def body(owner=None):
    """Начало ветки → «open» → [назначить владельца] → «step» → счётчик done → конец."""
    nodes = [node("h", "branch_head"), node("t1", "on:terminal.command", command="open"), node("t2", "on:terminal.command", command="step"),
             counter("d", "done"), node("o", "branch_out")]
    wires = [wire("h", "next", "t1"), wire("t2", "run", "d"), wire("d", "next", "o")]
    if owner is None:
        wires.append(wire("t1", "run", "t2"))
    else:
        nodes.append(node("own", "branch_owner", **owner))
        wires += [wire("t1", "run", "own"), wire("own", "next", "t2")]
    return {"title": "Ветвление", "nodes": nodes, "wires": wires}


class BranchingBase(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ivan, self.anna, self.boris = users.create_user("ivan"), users.create_user("anna"), users.create_user("boris")
        core = Machine.objects.create(name="Core", hostname="core")
        MachineProfile.objects.create(machine=core, login="root")

    def graph(self, doc, slug="branching"):
        graph = make(doc["nodes"], doc["wires"], slug=slug)
        graph.doc = doc
        graph.save()
        return graph

    def doc(self, owner=None, **fields):
        return {"nodes": [node("m", "manual"), node("b", "branching", group="g1", **fields)], "wires": [wire("m", "fire", "b")],
                "groups": {"g1": body({"who": "player"} if owner is None else owner)}}

    def cmd(self, user, command):
        emit("command.run", user, machine="core", login="root", command=command)

    def free(self):
        return Run.objects.filter(state__vacancy=True, status="running").count()

    def errors(self, graph):
        return [p for p in check.problems(graph.doc) if p["level"] == "error"]


class VacancyTests(BranchingBase):
    def test_sequence_with_limits(self):
        graph = self.graph(self.doc(repeat="yes", total=2, per=1))
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.boris)
        self.assertEqual(self.free(), 1)                           # В1 ждёт
        self.cmd(self.ivan, "open")
        self.assertEqual((self.free(), Branching.objects.get().taken), (1, 1))      # В1 занята, открылась В2
        self.cmd(self.ivan, "open")
        self.assertEqual((self.free(), Branching.objects.get().taken), (1, 1))      # у Ивана уже 1 из 1
        self.cmd(self.anna, "open")
        self.assertEqual((self.free(), Branching.objects.get().taken), (0, 2))      # лимит: новая не открывается
        self.cmd(self.boris, "open")
        self.assertEqual(Branching.objects.get().taken, 2)

    def test_owner_chain_hears_only_owner(self):
        start_manual(self.graph(self.doc(repeat="yes")), "m", self.boris)
        self.cmd(self.ivan, "open")
        self.cmd(self.anna, "step")                                # ветка Ивана чужой шаг не слышит
        self.assertEqual(count("done"), 0)
        self.cmd(self.ivan, "step")
        self.assertEqual(count("done"), 1)

    def test_each_player_has_own_chain(self):
        start_manual(self.graph(self.doc(repeat="yes")), "m", self.boris)
        self.cmd(self.ivan, "open")
        self.cmd(self.anna, "open")
        self.cmd(self.anna, "step")
        self.assertEqual(count("done"), 1)
        self.cmd(self.anna, "step")                                # у Анны цепочка уже закончилась
        self.assertEqual(count("done"), 1)
        self.cmd(self.ivan, "step")
        self.assertEqual(count("done"), 2)

    def test_per_initiator_two(self):
        start_manual(self.graph(self.doc(repeat="yes", per=2)), "m", self.boris)
        for _ in range(3):
            self.cmd(self.ivan, "open")
        self.assertEqual(Branching.objects.get().users, {str(self.ivan.pk): 2})

    def test_vacancy_survives_finished_parent(self):
        start_manual(self.graph(self.doc(repeat="yes")), "m", self.boris)
        self.assertEqual(Run.objects.get(node="m").status, "done")
        self.assertEqual(self.free(), 1)

    def test_no_second_vacancy_when_main_passes_again(self):
        graph = self.graph(self.doc(repeat="yes"))
        start_manual(graph, "m", self.boris)
        start_manual(graph, "m", self.boris)
        self.assertEqual(self.free(), 1)


class SingleBranchTests(BranchingBase):
    def test_free_branch_hears_anyone_then_owner(self):
        start_manual(self.graph(self.doc(repeat="no")), "m", self.boris)
        self.assertEqual(Branching.objects.count(), 0)
        self.cmd(self.anna, "open")                                # ничья ветка: слышит любого, но тот, кто сделал, её владелец
        self.cmd(self.ivan, "step")
        self.assertEqual(count("done"), 0)
        self.cmd(self.anna, "step")
        self.assertEqual(count("done"), 1)

    def test_without_owner_branch_stays_free(self):
        doc = self.doc(repeat="no")
        doc["groups"]["g1"] = body()
        start_manual(self.graph(doc), "m", self.boris)
        self.cmd(self.anna, "open")
        self.cmd(self.ivan, "step")
        self.assertEqual(count("done"), 1)


class OwnerTests(BranchingBase):
    def test_group_owner(self):
        graph = self.graph(self.doc(repeat="no", owner={"who": "crew", "crew": "red"}))
        crews.join(graph, "red", self.anna)
        crews.join(graph, "red", self.boris)
        start_manual(graph, "m", self.ivan)
        self.cmd(self.ivan, "open")                                # Иван открыл, но группа «red» — Анна и Борис
        self.cmd(self.ivan, "step")
        self.assertEqual(count("done"), 0)
        self.cmd(self.boris, "step")
        self.assertEqual(count("done"), 1)

    def test_unowner_frees_branch(self):
        doc = self.doc(repeat="no")
        g = doc["groups"]["g1"]
        g["nodes"].append(node("free", "branch_unowner"))
        g["wires"] = [wire("h", "next", "t1"), wire("t1", "run", "own"), wire("own", "next", "free"), wire("free", "next", "t2"),
                      wire("t2", "run", "d"), wire("d", "next", "o")]
        start_manual(self.graph(doc), "m", self.boris)
        self.cmd(self.ivan, "open")
        self.cmd(self.anna, "step")
        self.assertEqual(count("done"), 1)


class GateTests(BranchingBase):
    def doc_with_gates(self, **fields):
        doc = self.doc(repeat="yes", **fields)
        doc["nodes"] += [node("close", "manual"), node("shut", "branch_gate", mode="close"), node("open", "manual"), node("on", "branch_gate", mode="open")]
        doc["wires"] += [wire("close", "fire", "shut"), wire("b", "gate", "shut", "f:branches"), wire("open", "fire", "on"),
                         wire("b", "gate", "on", "f:branches")]
        return doc

    def test_close_removes_free_vacancy_open_returns_it(self):
        graph = self.graph(self.doc_with_gates())
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "open")
        start_manual(graph, "close", self.boris)
        self.assertEqual(self.free(), 0)
        self.cmd(self.anna, "open")                                # набор закрыт, вакансии нет
        self.assertEqual(Branching.objects.get().taken, 1)
        self.cmd(self.ivan, "step")                                # занятая ветка идёт
        self.assertEqual(count("done"), 1)
        start_manual(graph, "open", self.boris)
        self.assertEqual(self.free(), 1)

    def test_open_does_not_exceed_limit(self):
        graph = self.graph(self.doc_with_gates(total=1))
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "open")
        start_manual(graph, "open", self.boris)
        self.assertEqual(self.free(), 0)


class CheckTests(BranchingBase):
    def test_repeat_without_owner_warns(self):
        doc = self.doc(repeat="yes")
        doc["groups"]["g1"] = body()
        found = check.problems(doc)
        self.assertTrue(any(p["level"] == "warning" and "Повторять" in p["text"] for p in found))

    def test_no_head_is_error(self):
        doc = self.doc(repeat="no")
        doc["groups"]["g1"] = {"title": "x", "nodes": [], "wires": []}
        self.assertTrue(any(p["level"] == "error" and "Начала ветки" in p["text"] for p in check.problems(doc)))


class GateByNameTests(BranchingBase):
    def doc_named(self, name="Заявки", gate_name="Заявки"):
        doc = self.doc(repeat="yes", name=name)
        doc["nodes"] += [node("shut", "manual"), node("g", "branch_gate", mode="close", name=gate_name)]
        doc["wires"] += [wire("shut", "fire", "g")]
        return doc

    def test_gate_finds_branching_by_name(self):
        graph = self.graph(self.doc_named())
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.boris)
        self.assertEqual(self.free(), 1)
        start_manual(graph, "shut", self.boris)
        self.assertEqual(self.free(), 0)

    def test_unknown_name_is_error(self):
        doc = self.doc_named(gate_name="Нет такого")
        self.assertTrue(any(p["level"] == "error" and "нет ветвления" in p["text"] for p in check.problems(doc)))

    def test_no_name_no_wire_is_error(self):
        doc = self.doc_named(gate_name="")
        self.assertTrue(any(p["level"] == "error" and "Название ветвления" in p["text"] for p in check.problems(doc)))


def rows(*items):
    """Строки «Данных»: ("ключ", значение[, действие]) -> k1, k2…"""
    return [{"id": f"k{i}", "name": key, "value": rest[0] if rest else None, **({"op": rest[1]} if len(rest) > 1 else {})}
            for i, (key, *rest) in enumerate(items, 1)]


def put(i, *items, mode="set"):
    return node(i, "data_set", mode=mode, rows=rows(*items))


def read(i, *keys):
    return node(i, "data_get", rows=[{"id": f"k{n}", "name": key} for n, key in enumerate(keys, 1)])


class FlowDataTests(BranchingBase):
    """«Данные: Изменить» и «Данные: Значение ключа»: данные идут с потоком и копируются в новые ветки."""

    def doc_data(self, repeat="no"):
        inner = [node("h", "branch_head"), node("t1", "on:terminal.command", command="go"), read("dd", "color"),
                 node("c", "do:world_count", name="x"), node("o", "branch_out")]
        wires = [wire("h", "next", "t1"), wire("t1", "run", "c"), wire("dd", "k1", "c", "f:name"), wire("c", "next", "o")]
        return {"nodes": [node("m", "manual"), put("s", ("color", "red")), node("b", "branching", group="g1", repeat=repeat, per=1)],
                "wires": [wire("m", "fire", "s"), wire("s", "next", "b")], "groups": {"g1": {"title": "Ветвление", "nodes": inner, "wires": wires}}}

    def test_branch_reads_data_set_before_branching(self):
        graph = self.graph(self.doc_data())
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.boris)
        self.cmd(self.ivan, "go")
        self.assertEqual(count("red"), 1)

    def test_every_vacancy_gets_the_same_data(self):
        start_manual(self.graph(self.doc_data(repeat="yes")), "m", self.boris)
        self.cmd(self.ivan, "go")
        self.cmd(self.anna, "go")
        self.assertEqual(count("red"), 2)

    def test_branch_data_is_its_own(self):
        doc = self.doc_data()
        doc["groups"]["g1"]["nodes"].append(put("ch", ("color", "green")))
        g = doc["groups"]["g1"]
        g["wires"] = [wire("h", "next", "t1"), wire("t1", "run", "ch"), wire("ch", "next", "c"), wire("dd", "k1", "c", "f:name"), wire("c", "next", "o")]
        start_manual(self.graph(doc), "m", self.boris)
        self.cmd(self.ivan, "go")
        self.assertEqual((count("green"), count("red")), (1, 0))


class DataNodesTests(BranchingBase):
    """«Данные», «Данные: Изменить» (изменить, удалить, очистить) и «Данные: Значение ключа» в одном потоке и по проводу."""

    def run_flow(self, *middle, keys=("a",), name_from="k1"):
        """manual → middle… → счётчик с именем из значения ключа."""
        nodes = [node("m", "manual"), *middle, read("g", *keys), node("c", "do:world_count", name="x")]
        chain = ["m", *[n["id"] for n in middle], "c"]
        wires = [wire(chain[i], "fire" if i == 0 else "next", chain[i + 1]) for i in range(len(chain) - 1)]
        wires.append(wire("g", name_from, "c", "f:name"))
        graph = self.graph({"nodes": nodes, "wires": wires})
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.ivan)
        return graph

    def test_set_and_nested_path(self):
        self.run_flow(put("s", ("a.b", "deep")), keys=("a.b",))
        self.assertEqual(count("deep"), 1)

    def test_number_operations(self):
        graph = self.run_flow(put("s1", ("n", "5")), put("s2", ("n", "3", "add")), put("s3", ("n", "2", "sub")), keys=("n",))
        self.assertEqual(Run.objects.get(graph=graph).state["data"], {"n": 6})

    def test_list_push_and_pull(self):
        graph = self.run_flow(put("s1", ("l", "x", "push")), put("s2", ("l", "y", "push")), put("s3", ("l", "x", "pull")), keys=("l",))
        self.assertEqual(Run.objects.get(graph=graph).state["data"], {"l": ["y"]})

    def test_delete(self):
        graph = self.run_flow(put("s", ("a", "1"), ("b", "2")), put("d", ("a",), mode="delete"))
        self.assertEqual(Run.objects.get(graph=graph).state["data"], {"b": "2"})

    def test_clear(self):
        graph = self.run_flow(put("s", ("a", "1")), put("z", mode="clear"))
        self.assertEqual(Run.objects.get(graph=graph).state["data"], {})

    def test_wired_dict_is_a_pure_copy(self):
        """Провод «Данные» не трогает данные потока: изменённая копия идёт дальше по проводу."""
        nodes = [node("m", "manual"), node("d", "dict", rows=rows(("a", "one"))), put("p", ("b", "two")), read("g", "a", "b"), node("c", "do:world_count", name="x")]
        wires = [wire("m", "fire", "c"), wire("d", "value", "p", "in"), wire("p", "data", "g", "in"), wire("g", "k2", "c", "f:name")]
        graph = self.graph({"nodes": nodes, "wires": wires})
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.ivan)
        self.assertEqual(count("two"), 1)
        self.assertEqual(Run.objects.get(graph=graph).state.get("data") or {}, {})

    def test_wired_value_into_row(self):
        nodes = [node("m", "manual"), node("t", "text", value="hello"), put("s", ("a", None)), read("g", "a"), node("c", "do:world_count", name="x")]
        nodes[2]["data"]["rows"][0]["id"] = "k1"
        wires = [wire("m", "fire", "s"), wire("t", "value", "s", "f:k1"), wire("s", "next", "c"), wire("g", "k1", "c", "f:name")]
        graph = self.graph({"nodes": nodes, "wires": wires})
        start_manual(graph, "m", self.ivan)
        self.assertEqual(count("hello"), 1)

    def test_missing_key_is_empty(self):
        self.run_flow(put("s", ("a", "1")), keys=("nothing",))
        self.assertEqual(count(""), 0)


class StartOnceTests(BranchingBase):
    def test_player_start_fires_once_per_game(self):
        doc = {"nodes": [node("t", "on:terminal.command", command="go"), counter("c", "n")], "wires": [wire("t", "run", "c")]}
        self.graph(doc)
        self.cmd(self.ivan, "go")
        self.cmd(self.anna, "go")
        self.assertEqual(count("n"), 1)

    def test_world_events_start_every_time(self):
        doc = {"nodes": [node("m", "manual"), counter("c", "n")], "wires": [wire("m", "fire", "c")]}
        graph = self.graph(doc)
        start_manual(graph, "m", self.ivan)
        start_manual(graph, "m", self.ivan)
        self.assertEqual(count("n"), 2)
