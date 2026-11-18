"""Проверка сценария и сокеты нод."""
from django.test import SimpleTestCase

from graph import check, nodes


def node(node_id, kind, **data):
    return {"id": node_id, "type": kind, "x": 0, "y": 0, "data": data}


def wire(src, out, dst, inp="in"):
    return {"from": src, "out": out, "to": dst, "in": inp}


def texts(doc):
    return [(p["node"], p["text"]) for p in check.problems(doc)]


class SocketTests(SimpleTestCase):
    def test_many_and_tail(self):
        turns = nodes.KINDS["turns"]
        self.assertEqual(nodes.sockets(turns, {"count": 3, "cycle": "stop"}, "out"), ["b1", "b2", "b3", "over"])
        join = nodes.KINDS["join"]
        self.assertEqual(nodes.sockets(join, {"count": 3}, "in"), ["i1", "i2", "i3"])
        self.assertEqual(nodes.sockets(join, {"count": 1}, "in"), ["i1"])
        self.assertIn("timeout", nodes.sockets(nodes.KINDS["on:placement.opened"], {}, "out"))
        self.assertNotIn("timeout", nodes.sockets(nodes.KINDS["manual"], {}, "out"))

    def test_actions_come_from_engine_without_browser_and_host(self):
        self.assertIn("do:world_flag", nodes.KINDS)
        self.assertIn("do:letter", nodes.KINDS)
        self.assertNotIn("do:key", nodes.KINDS)                              # теперь «Размещение: Создать»
        self.assertNotIn("do:alert", nodes.KINDS)
        self.assertNotIn("do:goto", nodes.KINDS)

    def test_catalog(self):
        found = nodes.catalog()
        self.assertEqual({g["name"] for g in found["groups"]}, {"entity", "attr", "noun", "happen", "flow", "data", "action", "struct", "service"})
        attempt = next(k for k in found["kinds"] if k["name"] == "try:machine")
        self.assertEqual((attempt["owned"], attempt["outs"]), ("machine", []))


class CheckTests(SimpleTestCase):
    def test_ok_graph_has_no_problems(self):
        doc = {"nodes": [node("m", "manual"), node("a", "do:world_flag", name="door")], "wires": [wire("m", "fire", "a")]}
        self.assertEqual(texts(doc), [])

    def test_noun_used_only_as_reference_is_fine(self):
        doc = {"nodes": [node("m", "manual"), node("w", "ent:machine", machine="core"), node("a", "act:tag", variant="on")],
               "wires": [wire("m", "fire", "a"), wire("w", "value", "a", "f:name")]}
        self.assertEqual(texts(doc), [])

    def test_required_and_unknown(self):
        doc = {"nodes": [node("m", "on:tag"), node("x", "nope")], "wires": [wire("m", "set", "x")]}
        found = texts(doc)
        self.assertIn(("m", "не заполнено «Имя»"), found)
        self.assertIn(("x", "неизвестная нода «nope»"), found)

    def test_bad_sockets_and_ref(self):
        doc = {"nodes": [node("m", "manual"), node("f", "on:placement.opened", item="r"), node("a", "do:world_flag", name="x")],
               "wires": [wire("m", "nope", "a"), wire("f", "placement", "a", "f:name")]}
        found = texts(doc)
        self.assertIn(("m", "нет выхода «nope»"), found)
        self.assertIn(("a", "«Метка мира» ждёт метку мира, а приходит размещение"), found)

    def test_start_only_with_input_and_cycle(self):
        doc = {"nodes": [node("m", "manual"), node("t", "on:schedule", mode="daily", at="10:00"), node("a", "reroute"), node("b", "reroute")],
               "wires": [wire("m", "fire", "t"), wire("m", "fire", "a"), wire("a", "next", "b"), wire("b", "next", "a")]}
        found = texts(doc)
        self.assertTrue(any("только стартом" in text for _, text in found))
        self.assertTrue(any("цикл без ожидания" in text for _, text in found))

    def test_cycle_through_wait_is_fine(self):
        doc = {"nodes": [node("m", "manual"), node("w", "wait", minutes=1), node("a", "reroute")],
               "wires": [wire("m", "fire", "w"), wire("w", "next", "a"), wire("a", "next", "w")]}
        self.assertFalse(any("цикл" in text for _, text in texts(doc)))

    def test_condition_and_clock(self):
        doc = {"nodes": [node("m", "manual"), node("c", "check", condition="tag:x and ("), node("w", "wait", mode="until", at="25:00")],
               "wires": [wire("m", "fire", "c"), wire("c", "yes", "w")]}
        found = texts(doc)
        self.assertTrue(any(n == "c" and text.startswith("условие") for n, text in found))
        self.assertTrue(any(n == "w" and "ЧЧ:ММ" in text for n, text in found))
        doc = {"nodes": [node("m", "manual"), node("w", "wait", mode="until", at="2031-05-14 21:00"), node("b", "act:machine.change", variant="booted",
                                                                                                        machine="aether-main", booted="вчера")],
               "wires": [wire("m", "fire", "w"), wire("w", "next", "b")]}
        found = texts(doc)
        self.assertFalse(any(n == "w" for n, _ in found))
        self.assertTrue(any(n == "b" and "ГГГГ-ММ-ДД" in text for n, text in found))

    def test_no_start_warning(self):
        doc = {"nodes": [node("a", "reroute")], "wires": []}
        self.assertTrue(any("нет старта" in text for _, text in texts(doc)))

    def test_clean(self):
        doc = check.clean({"nodes": [{"id": 1, "type": "manual", "data": {"label": "go"}, "junk": 1}], "wires": [wire("1", "fire", "1"), wire("1", "fire", "1")]})
        self.assertEqual(doc["nodes"][0]["id"], "1")
        self.assertNotIn("junk", doc["nodes"][0])
        self.assertEqual(len(doc["wires"]), 1)
        with self.assertRaises(ValueError):
            check.clean({"nodes": [{"id": "a"}, {"id": "a"}]})
