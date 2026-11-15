"""Возможности: «Открыть» потоком и условием («Когда» — событие или да/нет), «Закрыть» возможность и группу, «всем»,
сущность «Возможность», проверка графа. Почтовая сторона — mail/tests/test_talk.py."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from graph import check, nodes as N, offers, runtime
from graph.models import Graph, Offer
from graph.tests.test_runtime import node, wire


def make(nodes, wires, slug="g"):
    graph = Graph.objects.create(slug=slug, title=slug, active=True, doc={"nodes": nodes, "wires": wires})
    runtime.rebuild_starts(graph)
    return graph


def opened(node_id, **data):
    return node(node_id, "act:offer.open", mode="new", address="guard@port", title=node_id, **data)


class OfferTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")

    def keys(self, user):
        return sorted(view.key for view in offers.visible(user) if view.open)

    def test_the_when_input_takes_an_event_or_a_condition(self):
        self.assertTrue(N.compatible("event", "event|bool"))
        self.assertTrue(N.compatible("bool", "event|bool"))
        self.assertTrue(N.compatible("number", "event|bool"))
        self.assertFalse(N.compatible("machine", "event|bool"))
        kind = N.KINDS["act:offer.open"]
        self.assertEqual(N.sock_type(kind, {}, "in", "in"), "event|bool")
        doc = {"nodes": [node("t", "ent:tag", owner="player", name="vip"), opened("a")], "wires": [wire("t", "on", "a")]}
        self.assertEqual([p for p in check.problems(doc) if p["level"] == "error"], [])
        self.assertEqual(runtime.Doc(doc).refs[("a", "in")], ("t", "on"))
        self.assertNotIn("a", runtime.Doc(doc).fed)

    def test_a_condition_opens_it_for_those_it_holds_for(self):
        make([node("t", "ent:tag", owner="player", name="vip"), opened("a", closed="hidden")], [wire("t", "on", "a")])
        self.assertEqual((self.keys(self.ivan), offers.visible(self.ivan)), ([], []))
        values.set_tag("player", self.ivan.pk, "vip")
        self.assertEqual((self.keys(self.ivan), self.keys(self.anna)), (["g:a"], []))

    def test_open_for_the_player_or_for_all_and_close_a_group(self):
        graph = make([node("m", "manual"), opened("a", group="s"), opened("b", group="s", scope="all"), opened("c", show="mystery"),
                      node("x", "act:offer.close", variant="group", group="s")],
                     [wire("m", "fire", "a"), wire("a", "next", "b"), wire("b", "next", "c")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual((self.keys(self.ivan), self.keys(self.anna)), (["g:a", "g:b"], ["g:b"]))
        self.assertEqual([v.open for v in offers.visible(self.ivan) if v.key == "g:c"], [False])      # «???»
        view = next(v for v in offers.visible(self.ivan) if v.key == "g:a")
        self.assertEqual(offers.attempt(view, self.ivan, True), ("ok", None))
        self.assertEqual((self.keys(self.ivan), self.keys(self.anna)), ([], ["g:b"]))                  # группа закрыта только ему
        offers.close(graph, "b")
        self.assertEqual(self.keys(self.anna), [])
        self.assertFalse(Offer.objects.filter(node="b").exists())

    def test_close_by_wire_and_the_entity(self):
        graph = make([node("m", "manual"), opened("a", attempts=3), node("e", "ent:offer"), node("n", "number"),
                      node("go", "manual"), node("x", "act:offer.close", variant="offer"), node("k", "act:count", variant="set", owner="world", name="left")],
                     [wire("m", "fire", "a"), wire("a", "next", "k"), wire("a", "offer", "e", "f:offer"), wire("e", "left", "k", "f:value"),
                      wire("go", "fire", "x"), wire("a", "offer", "x", "f:offer")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(values.get("count", "world", 0, "left"), 3)
        runtime.start_manual(graph, "go", self.ivan)
        self.assertEqual(self.keys(self.ivan), [])

    def test_attempts_run_out(self):
        graph = make([node("m", "manual"), opened("a", attempts=2)], [wire("m", "fire", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        view = offers.visible(self.ivan)[0]
        self.assertEqual(offers.attempt(view, self.ivan, False), ("wrong", 1))
        view = offers.visible(self.ivan)[0]
        self.assertEqual(offers.attempt(view, self.ivan, False), ("exhausted", 0))
        self.assertEqual(offers.visible(self.ivan), [])
        runtime.start_manual(graph, "m", self.ivan)                                  # открыть снова — попытки сначала
        self.assertEqual(offers.visible(self.ivan)[0].left, 2)
        self.assertTrue(graph)

    def test_the_used_node_filters_result_offer_group_and_word(self):
        from engine.events import emit

        make([node("u", "on:offer.used", offer="g:a", word="склад*", repeat="always"), node("c", "do:world_count", name="c")], [wire("u", "ok", "c")])
        emit("offer.used", self.ivan, offer="g:a", result="wrong", words=["склад 7"])
        emit("offer.used", self.ivan, offer="g:b", result="ok", words=["склад 7"])
        emit("offer.used", self.ivan, offer="g:a", result="ok", words=["дом"])
        emit("offer.used", self.ivan, offer="g:a", result="ok", words=["Склад 7"])
        self.assertEqual(values.get("count", "world", 0, "c"), 1)
