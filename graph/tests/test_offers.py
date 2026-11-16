"""Возможности: сущность «Возможность» (что предлагается), «Открыть» потоком и условием («Когда» — событие или да/нет),
«Закрыть» возможность и группу, «всем», выходы «Использована» по сущности (каналы, развилки), проверка графа.
Почтовая сторона — mail/tests/test_talk.py, остальные каналы — test_offer_channels.py."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from graph import check, nodes as N, offers, runtime
from graph.models import Graph, Offer
from graph.tests.test_runtime import counter, node, wire


def make(nodes, wires, slug="g"):
    graph = Graph.objects.create(slug=slug, title=slug, active=True, doc={"nodes": nodes, "wires": wires})
    runtime.rebuild_starts(graph)
    return graph


def offer(node_id, **data):
    """Сущность «Возможность»: новое письмо guard@port."""
    return node(node_id, "ent:offer", mode="new", to="guard@port", title=node_id, **data)


def opener(node_id, target, **data):
    return node(node_id, "act:offer", offer=f"g:{target}", **data)


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
        kind = N.KINDS["act:offer"]
        self.assertEqual(N.sock_type(kind, {}, "in", "in"), "event|bool")
        doc = {"nodes": [node("t", "ent:tag", owner="player", name="vip"), offer("a"), node("o", "act:offer")],
               "wires": [wire("t", "on", "o"), wire("a", "offer", "o", "f:offer")]}
        self.assertEqual([p for p in check.problems(doc) if p["level"] == "error"], [])
        self.assertEqual(runtime.Doc(doc).refs[("o", "in")], ("t", "on"))
        self.assertNotIn("o", runtime.Doc(doc).fed)
        alien = {"nodes": [node("t", "ent:tag", owner="player", name="vip"), node("o", "act:offer", offer="other:a")], "wires": [wire("t", "on", "o")]}
        self.assertIn("по условию открываются только возможности этого сценария", [p["text"] for p in check.problems(alien, slug="g")])

    def test_a_condition_with_show_shows_a_locked_variant(self):
        make([node("t", "ent:tag", owner="player", name="vip"), offer("a"), node("o", "act:offer", state="mystery")],
             [wire("t", "on", "o"), wire("a", "offer", "o", "f:offer")])
        self.assertEqual(offers.visible(self.ivan), [])
        values.set_tag("player", self.ivan.pk, "vip")
        self.assertEqual([(v.key, v.open) for v in offers.visible(self.ivan)], [("g:a", False)])

    def test_a_condition_opens_it_for_those_it_holds_for(self):
        make([node("t", "ent:tag", owner="player", name="vip"), offer("a"), node("o", "act:offer")],
             [wire("t", "on", "o"), wire("a", "offer", "o", "f:offer")])
        self.assertEqual((self.keys(self.ivan), offers.visible(self.ivan)), ([], []))
        values.set_tag("player", self.ivan.pk, "vip")
        self.assertEqual((self.keys(self.ivan), self.keys(self.anna)), (["g:a"], []))

    def test_open_for_the_player_or_for_all_and_close_a_group(self):
        graph = make([node("m", "manual"), offer("a", group="s"), offer("b", group="s"), offer("c"),
                      opener("oa", "a"), opener("ob", "b", scope="all"), opener("oc", "c", state="mystery"), node("go", "manual"), opener("od", "c")],
                     [wire("m", "fire", "oa"), wire("oa", "next", "ob"), wire("ob", "next", "oc"), wire("go", "fire", "od")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual((self.keys(self.ivan), self.keys(self.anna)), (["g:a", "g:b"], ["g:b"]))
        self.assertEqual([v.open for v in offers.visible(self.ivan) if v.key == "g:c"], [False])      # «???» видна и при «Скрыть»
        runtime.start_manual(graph, "go", self.ivan)
        self.assertEqual([v.open for v in offers.visible(self.ivan) if v.key == "g:c"], [True])       # «Открыть» раскрывает
        view = next(v for v in offers.visible(self.ivan) if v.key == "g:a")
        self.assertEqual(offers.settle(view, self.ivan, False), "wrong")                               # неверный ответ ничего не закрывает
        self.assertEqual(offers.settle(view, self.ivan, True), "ok")
        self.assertEqual((self.keys(self.ivan), self.keys(self.anna)), (["g:c"], ["g:b"]))             # группа закрыта только ему
        offers.close(graph, "b")
        self.assertEqual(self.keys(self.anna), [])
        self.assertFalse(Offer.objects.filter(node="b").exists())

    def test_one_offer_opened_from_two_places_and_closed_by_wire(self):
        graph = make([node("m", "manual"), node("m2", "manual"), offer("a", text="hello {{name}}"), node("o1", "act:offer"), node("o2", "act:offer"),
                      node("go", "manual"), node("x", "act:offer", state="hidden")],
                     [wire("m", "fire", "o1"), wire("m2", "fire", "o2"), wire("a", "offer", "o1", "f:offer"), wire("a", "offer", "o2", "f:offer"),
                      wire("go", "fire", "x"), wire("a", "offer", "x", "f:offer")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(self.keys(self.ivan), ["g:a"])
        self.assertEqual(offers.visible(self.ivan)[0].spec["text"], "hello {{name}}")
        runtime.start_manual(graph, "go", self.ivan)
        self.assertEqual(self.keys(self.ivan), [])
        runtime.start_manual(graph, "m2", self.ivan)
        self.assertEqual(self.keys(self.ivan), ["g:a"])

    def test_open_fails_without_an_offer_entity(self):
        graph = make([node("m", "manual"), node("o", "act:offer", offer="g:m"), node("c", "do:world_count", name="c")],
                     [wire("m", "fire", "o"), wire("o", "fail", "c")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual((counter(), Offer.objects.count()), (1, 0))

    def test_the_used_outputs_follow_the_entity(self):
        doc = runtime.Doc({"nodes": [offer("a", text="Код {{1}} [[док: 7|9]], [[день|ночь]] в 12:00"), node("u", "on:offer.used"),
                                     node("w", "ent:offer", channel="choice", buttons=["Yes", "No"]), node("v", "on:offer.used", offer="g:w"),
                                     node("f", "ent:offer", channel="file"), node("z", "on:offer.used", offer="g:f")],
                           "wires": [wire("a", "offer", "u", "f:offer")]})
        self.assertEqual(offers.used_iface(doc, "u", "g")["outputs"], ["ok", "wrong", "fork:док", "fork:2"])
        self.assertEqual(offers.used_iface(doc, "u", "g")["labels"]["fork:2"], "Развилка 2")
        self.assertEqual(offers.used_iface(doc, "v", "g")["labels"], {"b1": "Yes", "b2": "No"})
        self.assertEqual(offers.used_iface(doc, "z", "g")["labels"], {"ok": "Нажата"})
        self.assertIsNone(offers.used_iface(doc, "v", "other"))
        bad = {"nodes": [node("w", "ent:offer", channel="choice", buttons=["Yes"]), node("v", "on:offer.used", offer="g:w"), node("c", "do:world_count", name="c")],
               "wires": [wire("v", "wrong", "c")]}
        self.assertTrue([p for p in check.problems(bad, slug="g") if p["level"] == "error"])

    def test_a_fork_word_and_a_button_lead_their_own_way(self):
        make([offer("a", text="[[док: 7|9]]"), node("u", "on:offer.used", repeat="always"), node("eq", "compare", op="eq", b="7"), node("k", "check"),
              node("c", "do:world_count", name="c"),
              node("w", "ent:offer", channel="choice", buttons=["Yes", "No"]), node("v", "on:offer.used", repeat="always"), node("n", "do:world_count", name="n")],
             [wire("a", "offer", "u", "f:offer"), wire("u", "ok", "k"), wire("u", "fork:док", "eq", "f:a"), wire("eq", "value", "k", "f:condition"),
              wire("k", "yes", "c"), wire("w", "offer", "v", "f:offer"), wire("v", "b2", "n")])
        emit("offer.used", self.ivan, offer="g:a", result="ok", outs=["ok"], forks={"док": "9"})
        emit("offer.used", self.ivan, offer="g:a", result="wrong", outs=["wrong"], forks={"док": "7"})
        emit("offer.used", self.ivan, offer="g:b", result="ok", outs=["ok"], forks={"док": "7"})
        self.assertEqual(counter(), 0)
        emit("offer.used", self.ivan, offer="g:a", result="ok", outs=["ok"], forks={"док": "7"})
        self.assertEqual(counter(), 1)
        emit("offer.used", self.ivan, offer="g:w", result="ok", outs=["ok", "b1"])
        self.assertEqual(counter("n"), 0)
        emit("offer.used", self.ivan, offer="g:w", result="ok", outs=["ok", "b2"])
        self.assertEqual(counter("n"), 1)

    def test_states_stack_and_hide_by_event_wins(self):
        graph = make([node("y", "boolean", value=True), node("t", "ent:tag", owner="player", name="vip"), offer("a", group="g1"), offer("b", group="g1"),
                      node("q", "act:offer", state="mystery"), node("o", "act:offer"), node("ob", "act:offer", offer="g:b"),
                      node("m", "manual"), node("h", "act:offer", state="hidden", whole="group"), node("m2", "manual")],
                     [wire("y", "value", "q"), wire("t", "on", "o"), wire("a", "offer", "q", "f:offer"), wire("a", "offer", "o", "f:offer"),
                      wire("m2", "fire", "ob"), wire("m", "fire", "h"), wire("a", "offer", "h", "f:offer")])
        self.assertEqual([(v.key, v.open) for v in offers.visible(self.ivan)], [("g:a", False)])           # «???», пока условия нет
        values.set_tag("player", self.ivan.pk, "vip")
        self.assertEqual([(v.key, v.open) for v in offers.visible(self.ivan)], [("g:a", True)])            # самое открытое
        runtime.start_manual(graph, "m2", self.ivan)
        self.assertEqual(self.keys(self.ivan), ["g:a", "g:b"])
        runtime.start_manual(graph, "m", self.ivan)                                                       # скрыть всю группу
        self.assertEqual((offers.visible(self.ivan), self.keys(self.anna)), ([], []))
        alien = {"nodes": [node("y", "boolean", value=True), offer("a"), node("h", "act:offer", state="hidden")],
                 "wires": [wire("y", "value", "h"), wire("a", "offer", "h", "f:offer")]}
        self.assertIn("«Скрыть» — только по событию: без условия возможность и так скрыта", [p["text"] for p in check.problems(alien, slug="g")])

    def test_an_offer_for_an_account_is_one_conversation_for_everyone_on_it(self):
        from machines.models import Machine, MachineProfile

        port = Machine.objects.create(name="Port", hostname="port")
        MachineProfile.objects.create(machine=port, login="guard", name="Guard", freq=1)
        graph = make([node("m", "manual"), offer("a", group="ask"), offer("b", group="ask"),
                      node("o", "act:offer", offer=["g:a", "g:b"], scope="account", account="guard@port")], [wire("m", "fire", "o")])
        runtime.start_manual(graph, "m", self.ivan)
        mine = offers.visible(self.ivan, "port", "guard")
        self.assertEqual(sorted(v.key for v in mine), ["g:a", "g:b"])
        self.assertEqual(sorted(v.key for v in offers.visible(self.anna, "port", "guard")), ["g:a", "g:b"])     # видят все на учётке
        self.assertEqual(offers.visible(self.anna, "port", "other"), [])                                      # с другой — нет
        self.assertEqual(offers.settle(next(v for v in mine if v.key == "g:a"), self.ivan, True), "ok")
        self.assertEqual(offers.visible(self.anna, "port", "guard"), [])        # верный ответ одного скрыл вариант (и группу) у всех

    def test_hide_a_group_by_its_name(self):
        graph = make([node("m", "manual"), offer("a", group="ask"), offer("b", group="ask"), offer("c"), node("o", "act:offer", offer=["g:a", "g:b", "g:c"]),
                      node("h", "act:offer", state="hidden", whole="group", offer="ask")], [wire("m", "fire", "o"), wire("o", "next", "h")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(self.keys(self.ivan), ["g:c"])

    def test_open_a_group_by_name_or_by_an_offer(self):
        graph = make([node("m", "manual"), offer("a", group="ask"), offer("b", group="ask"), offer("c", group="other"), offer("d"),
                      node("o", "act:offer", whole="group", offer="ask"), node("q", "act:offer", state="mystery", whole="group")],
                     [wire("m", "fire", "o"), wire("o", "next", "q"), wire("c", "offer", "q", "f:offer")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(sorted((v.key, v.open) for v in offers.visible(self.ivan)), [("g:a", True), ("g:b", True), ("g:c", False)])

    def test_a_group_by_condition(self):
        make([node("y", "boolean", value=True), offer("a", group="ask"), offer("b", group="ask"), offer("c"),
              node("o", "act:offer", whole="group", offer=["ask"])], [wire("y", "value", "o")])
        self.assertEqual(self.keys(self.ivan), ["g:a", "g:b"])

    def test_a_letter_on_the_input_drops_new(self):
        self.assertEqual(offers.spec_of({"mode": "new", "letter": "x"})["mode"], "reply")
        self.assertEqual(offers.spec_of({"mode": "forward"})["mode"], "forward")
        self.assertEqual(N.KINDS["ent:offer"].inline, {"letter": ("mode", ("new",))})

    def test_fork_names(self):
        self.assertEqual(offers.fork("док: 7|9"), ("док", ["7", "9"]))
        self.assertEqual(offers.fork("12:00|13:00"), ("", ["12:00", "13:00"]))
        self.assertEqual(offers.fork_values("[[a|b]] и [[время: 12:00|13:00]]", ["b", "13:00"]), {"1": "b", "время": "13:00"})
