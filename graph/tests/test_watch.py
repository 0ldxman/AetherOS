"""«Наблюдение»: ветки по событиям, «Пока»-фильтр, «Снять наблюдение» снаружи и изнутри, ветки снимаются или доживают."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from graph import check
from graph.models import Graph, Run, Wait
from graph.runtime import rebuild_starts, start_manual
from graph.tests.test_runtime import node, wire


def count(name):
    return values.get(values.COUNT, "world", 0, name)


def graph(outer, outer_wires, inner, inner_wires, slug="w"):
    g = Graph.objects.create(slug=slug, title=slug, active=True,
                             doc={"nodes": outer, "wires": outer_wires, "groups": {"g1": {"title": "Наблюдение", "nodes": inner, "wires": inner_wires}}})
    rebuild_starts(g)
    return g


TAGGER = ([node("c", "on:terminal.command", command="hi"), node("t", "act:tag", variant="on", owner="player", name="seen")],
          [wire("c", "run", "t")])


class WatchTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ivan, self.anna = users.create_user("ivan"), users.create_user("anna")

    def test_from_activation_every_event_is_a_branch_with_its_initiator(self):
        g = graph([node("w", "watch", group="g1"), node("d", "do:world_count", name="done")], [wire("w", "done", "d")], *TAGGER)
        self.assertEqual([p for p in check.problems(g.doc) if p["level"] == "error"], [])
        emit("command.run", self.ivan, machine="core", login="a", command="hi")
        emit("command.run", self.anna, machine="core", login="b", command="hi")
        emit("command.run", self.ivan, machine="core", login="a", command="hi")
        self.assertTrue(values.on("player", self.ivan.pk, "seen") and values.on("player", self.anna.pk, "seen"))
        holder = Run.objects.get(parent__isnull=True)
        self.assertEqual(holder.state["vals"]["w"], {"count": 3, "initiators": ["ivan", "anna"]})
        self.assertEqual(Run.objects.filter(parent=holder).count(), 3)
        rebuild_starts(g)                                    # пересохранили — второй держатель не появляется
        self.assertEqual(Run.objects.filter(parent__isnull=True).count(), 1)

    def test_while_is_a_filter(self):
        graph([node("w", "watch", group="g1", **{"while": "tag:world:alarm"})], [], *TAGGER)
        emit("command.run", self.ivan, machine="core", login="a", command="hi")
        self.assertFalse(values.on("player", self.ivan.pk, "seen"))
        values.set_tag("world", 0, "alarm")
        emit("command.run", self.ivan, machine="core", login="a", command="hi")
        self.assertTrue(values.on("player", self.ivan.pk, "seen"))

    def test_stop_from_outside_cancels_branches_and_goes_on(self):
        inner = [node("c", "on:terminal.command", command="hi"), node("x", "on:terminal.command", command="never"),
                 node("t", "do:world_count", name="late")]
        g = graph([node("m", "manual"), node("w", "watch", group="g1"), node("s", "signal", name="close"), node("d", "do:world_count", name="done")],
                  [wire("m", "fire", "w"), wire("s", "got", "w", "stop"), wire("w", "done", "d")],
                  inner, [wire("c", "run", "x"), wire("x", "run", "t")])
        start_manual(g, "m")
        emit("command.run", self.ivan, machine="core", login="a", command="hi")
        self.assertEqual(Run.objects.filter(parent__isnull=False, status="running").count(), 1)      # ветка ждёт never
        emit("signal", None, signal="close")
        self.assertEqual(count("done"), 1)
        self.assertFalse(Run.objects.filter(status="running").exists())
        self.assertFalse(Wait.objects.exists())
        emit("command.run", self.ivan, machine="core", login="a", command="hi")                      # больше не ловит
        self.assertEqual(Run.objects.filter(parent__isnull=False).count(), 1)

    def test_stop_inside_keeps_the_stopper_and_branches_may_live(self):
        inner = [node("c", "on:terminal.command", command="wait"), node("x", "on:terminal.command", command="later", own="player"),
                 node("t", "do:world_count", name="later"),
                 node("k", "on:terminal.command", command="win"), node("s", "watch_stop"), node("p", "do:world_count", name="prize")]
        g = graph([node("m", "manual"), node("w", "watch", group="g1", branches="keep"), node("d", "do:world_count", name="done")],
                  [wire("m", "fire", "w"), wire("w", "done", "d")],
                  inner, [wire("c", "run", "x"), wire("x", "run", "t"), wire("k", "run", "s"), wire("s", "next", "p")])
        start_manual(g, "m")
        emit("command.run", self.ivan, machine="core", login="a", command="wait")
        emit("command.run", self.anna, machine="core", login="b", command="win")
        self.assertEqual((count("prize"), count("done")), (1, 1))
        emit("command.run", self.ivan, machine="core", login="a", command="later")                   # ветка Ивана дожила
        self.assertEqual(count("later"), 1)
