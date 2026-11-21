"""«Переменная: Значение» и «Переменная: Изменить»: общие переменные сценария."""
from graph import check
from graph.models import Shared
from graph.runtime import start_manual
from graph.tests.test_branching import BranchingBase, count, rows
from graph.tests.test_runtime import node, wire


def setv(i, *items, mode="set", op=None):
    return node(i, "var_set", mode=mode, rows=rows(*items), **({"op": op} if op else {}))


def getv(i, *keys):
    return node(i, "var_get", rows=[{"id": f"k{n}", "name": key} for n, key in enumerate(keys, 1)])


class VariableTests(BranchingBase):
    def play(self, *middle, keys=("a",)):
        """manual → middle… → счётчик с именем из переменной."""
        nodes = [node("m", "manual"), *middle, getv("g", *keys), node("c", "do:world_count", name="x")]
        chain = ["m", *[n["id"] for n in middle], "c"]
        wires = [wire(chain[i], "fire" if i == 0 else "next", chain[i + 1]) for i in range(len(chain) - 1)] + [wire("g", "k1", "c", "f:name")]
        graph = self.graph({"nodes": nodes, "wires": wires})
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.ivan)
        return graph

    def data(self, graph):
        return Shared.objects.get(graph=graph).data

    def test_set_and_read_nested(self):
        self.play(setv("s", ("a.b", "deep")), keys=("a.b",))
        self.assertEqual(count("deep"), 1)

    def test_operations(self):
        graph = self.play(setv("s1", ("n", "5")), setv("s2", ("n", "3"), mode="op"), setv("s3", ("n", "2"), mode="op", op="sub"),
                          setv("s4", ("l", "x"), mode="op", op="push"), setv("s5", ("l", "y"), mode="op", op="push"), setv("s6", ("l", "x"), mode="op", op="pull"))
        self.assertEqual(self.data(graph), {"n": 6, "l": ["y"]})

    def test_delete_and_clear(self):
        graph = self.play(setv("s", ("a", "1"), ("b", "2")), setv("d", ("a",), mode="delete"))
        self.assertEqual(self.data(graph), {"b": "2"})
        graph = self.play2_clear()
        self.assertEqual(self.data(graph), {})

    def play2_clear(self):
        nodes = [node("m", "manual"), setv("s", ("a", "1")), setv("z", mode="clear")]
        graph = self.graph({"nodes": nodes, "wires": [wire("m", "fire", "s"), wire("s", "next", "z")]}, slug="clear")
        start_manual(graph, "m", self.ivan)
        return graph

    def test_shared_between_runs(self):
        """Переменная живёт в сценарии: второй запуск читает то, что записал первый."""
        nodes = [node("m", "manual"), setv("s", ("n", "1"), mode="op"), getv("g", "n"), node("c", "do:world_count", name="x")]
        graph = self.graph({"nodes": nodes, "wires": [wire("m", "fire", "s"), wire("s", "next", "c"), wire("g", "k1", "c", "f:name")]})
        start_manual(graph, "m", self.ivan)
        start_manual(graph, "m", self.anna)
        self.assertEqual(self.data(graph), {"n": 2})
        self.assertEqual(count("2"), 1)

    def test_missing_is_empty(self):
        self.play(setv("s", ("a", "1")), keys=("nothing",))
        self.assertEqual(count(""), 0)


class VariableConditionTests(BranchingBase):
    """Условия «var:имя>=3», «var:имя=текст» в «Если» и «Ждать условие»."""

    def branch(self, condition, *writes):
        """manual → записи… → «Если» → счётчики yes / no."""
        nodes = [node("m", "manual"), *writes, node("c", "check", condition=condition), node("y", "do:world_count", name="yes"), node("n", "do:world_count", name="no")]
        chain = ["m", *[w["id"] for w in writes], "c"]
        wires = [wire(chain[i], "fire" if i == 0 else "next", chain[i + 1]) for i in range(len(chain) - 1)] + [wire("c", "yes", "y"), wire("c", "no", "n")]
        graph = self.graph({"nodes": nodes, "wires": wires})
        self.assertEqual(self.errors(graph), [])
        start_manual(graph, "m", self.ivan)

    def test_number_compare(self):
        self.branch("var:keys>=3", setv("s", ("keys", "3")))
        self.assertEqual((count("yes"), count("no")), (1, 0))

    def test_below_threshold(self):
        self.branch("var:keys>=3", setv("s", ("keys", "2")))
        self.assertEqual((count("yes"), count("no")), (0, 1))

    def test_equals_text_and_list(self):
        self.branch("var:team=red and var:who=ivan", setv("a", ("team", "red")), setv("b", ("who", "ivan"), mode="op", op="push"))
        self.assertEqual(count("yes"), 1)

    def test_exists_and_not(self):
        self.branch("not var:nothing and var:there", setv("s", ("there", "1")))
        self.assertEqual(count("yes"), 1)

    def test_nested_path(self):
        self.branch("var:red.points>5", setv("s", ("red.points", "6")))
        self.assertEqual(count("yes"), 1)

    def test_wait_wakes_on_write_without_tick(self):
        graph = self.graph({"nodes": [node("a", "manual"), node("w", "wait_cond", condition="var:keys>=2"), node("c", "do:world_count", name="woke"),
                                      node("b", "manual"), setv("s", ("keys", "1"), mode="op")],
                            "wires": [wire("a", "fire", "w"), wire("w", "next", "c"), wire("b", "fire", "s")]})
        start_manual(graph, "a", self.ivan)
        start_manual(graph, "b", self.anna)
        self.assertEqual(count("woke"), 0)
        start_manual(graph, "b", self.boris)
        self.assertEqual(count("woke"), 1)

    def test_unwritten_variable_is_warned(self):
        doc = {"nodes": [node("m", "manual"), getv("g", "kyes"), node("c", "check", condition="var:keys>=1"), setv("s", ("keys", "1"))],
               "wires": [wire("m", "fire", "c")]}
        texts = [p["text"] for p in check.problems(doc) if p["level"] == "warning"]
        self.assertTrue(any("«kyes»" in t for t in texts))
        self.assertFalse(any("«keys»" in t for t in texts))
