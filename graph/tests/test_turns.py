"""«Направить: По очереди»: общий счёт на ноду и счёт у каждого инициатора."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from graph.runtime import start_manual
from graph.tests.test_runtime import make, node, wire


def count(name):
    return values.get(values.COUNT, "world", 0, name)


class TurnsScopeTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ivan, self.anna = users.create_user("ivan"), users.create_user("anna")

    def graph(self, **fields):
        return make([node("m", "manual"), node("t", "turns", count=3, **fields), node("a", "do:world_count", name="one"), node("b", "do:world_count", name="two"),
                     node("c", "do:world_count", name="three")],
                    [wire("m", "fire", "t"), wire("t", "b1", "a"), wire("t", "b2", "b"), wire("t", "b3", "c")])

    def test_shared_counts_all_players_together(self):
        graph = self.graph()
        for user in (self.ivan, self.anna, self.ivan):
            start_manual(graph, "m", user)
        self.assertEqual((count("one"), count("two"), count("three")), (1, 1, 1))

    def test_initiator_has_own_counter(self):
        graph = self.graph(scope="player")
        for user in (self.ivan, self.anna, self.ivan):
            start_manual(graph, "m", user)
        self.assertEqual((count("one"), count("two"), count("three")), (2, 1, 0))      # ivan: 1-я и 2-я ветки, anna: своя первая

    def test_initiator_cycles_on_its_own(self):
        graph = self.graph(scope="player")
        for _ in range(4):
            start_manual(graph, "m", self.ivan)
        self.assertEqual((count("one"), count("two"), count("three")), (2, 1, 1))
