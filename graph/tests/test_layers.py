"""Слои файла игрока в графе: «Размещение → Слои», «Слой», «Слой: Изменён», «Слой: Изменить»."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from engine.models import Event
from filesystem.testing import make_file
from graph import check, runtime
from graph.models import Run
from graph.runtime import Doc, value_of
from graph.tests.test_runtime import counter, make, node, wire
from machines.models import Machine, MachineProfile

KEY = "ivan@main:/home/ivan/vault.bin"


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


class LayerNodeTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.main = Machine.objects.create(name="Main", hostname="main")
        MachineProfile.objects.create(machine=self.main, user=self.ivan, name="Ivan", login="ivan", freq=1)
        make_file(self.main, "/home/ivan/vault.bin", state="> binary utf16\n> encrypted hunter2")
        self.run = type("R", (), {"user": self.ivan, "state": {}, "ctx": {}})()

    def get(self, nodes_, wires, node_id, out="value"):
        return value_of(self.run, Doc({"nodes": nodes_, "wires": wires}), node_id, out)

    def layer(self, key, out):
        return self.get([node("l", "ent:layer", layer=key)], [], "l", out)

    def act(self, variant, layer=KEY, **data):
        graph = make([node("m", "manual"), node("a", "act:layer", variant=variant, layer=layer, **data)], [wire("m", "fire", "a")],
                     slug=f"g{Run.objects.count()}")
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        return Run.objects.order_by("-pk").first().state["vals"]["a"]["layer"]

    def test_placement_lists_layers_and_layer_tells_about_itself(self):
        found = self.get([node("p", "ent:placement", placement=KEY)], [], "p", "layers")
        self.assertEqual(found, [f"{KEY}#c1", f"{KEY}#c2"])
        self.assertEqual([self.layer(f"{KEY}#c2", out) for out in ("type", "index", "removed", "added", "placement")],
                         ["encrypted", 2, False, False, KEY])

    def test_remove_below_top_takes_everything_above(self):
        self.assertEqual(self.act("remove", layer=f"{KEY}#c2"), f"{KEY}#c2")
        self.assertTrue(self.layer(f"{KEY}#c1", "removed") and self.layer(f"{KEY}#c2", "removed"))
        self.assertEqual([e.data["id"] for e in Event.objects.filter(name="layer.removed").order_by("pk")], ["c1", "c2"])

    def test_add_on_top_then_reset(self):
        graph = make([node("m", "manual"), node("a", "act:placement", variant="add_layer", placement=KEY, type="damaged")], [wire("m", "fire", "a")],
                     slug="add")
        runtime.start_manual(graph, "m", self.ivan)
        layers = self.get([node("p", "ent:placement", placement=KEY)], [], "p", "layers")
        self.assertEqual(layers[0], f"{KEY}#a1")
        self.assertTrue(self.layer(f"{KEY}#a1", "added"))
        self.assertEqual(Event.objects.filter(name="layer.added").count(), 1)
        self.act("quiet", layer=KEY)                                       # размещение — его верхний слой
        self.assertTrue(self.layer(f"{KEY}#a1", "removed"))
        self.act("remove", layer=KEY)
        self.assertTrue(self.layer(f"{KEY}#c1", "removed"))
        graph = make([node("m", "manual"), node("a", "act:placement", variant="reset_layers", placement=KEY)], [wire("m", "fire", "a")], slug="reset")
        runtime.start_manual(graph, "m", self.ivan)
        self.assertFalse(self.layer(f"{KEY}#c1", "removed"))

    def test_changed_event_by_layer_or_placement(self):
        graph = make([node("m", "manual"), node("w", "on:layer.changed", layer=f"{KEY}#c2"), node("a", "do:world_count", name="c"),
                      node("t", "act:tag", variant="on", name="typed")],
                     [wire("m", "fire", "w"), wire("w", "attempt", "a"), wire("a", "next", "t"), f("w", "given", "t", "name")])
        runtime.start_manual(graph, "m", self.ivan)
        emit("layer.attempt", self.ivan, machine="main", login="ivan", path="/home/ivan/vault.bin", layer="binary", id="c1", given="x")
        self.assertEqual(counter(), 0)
        emit("layer.attempt", self.ivan, machine="main", login="ivan", path="/home/ivan/vault.bin", layer="encrypted", id="c2", given="qwerty")
        self.assertEqual(counter(), 1)
        self.assertTrue(values.on("world", 0, "qwerty"))
