"""«Пока»: условие игрока и мира стало верным или ложным; действие с условием во «Когда» — делать, пока верно, и отменить."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from graph import check, runtime
from graph.tests.test_runtime import counter, make, node, wire
from machines.models import Machine
from world.models import WorldMoment


class WhileTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")

    def test_a_player_condition_turns_true_and_false(self):
        graph = make([node("w", "while", condition="tag:vip"), node("t", "do:world_count", name="c"), node("f", "do:world_count", name="d")],
                     [wire("w", "true", "t"), wire("w", "false", "f")])
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        values.set_tag("player", self.anna.pk, "x")                                  # ложно и было ложно — ничего
        self.assertEqual((counter("c"), counter("d")), (0, 0))
        values.set_tag("player", self.ivan.pk, "vip")
        self.assertEqual((counter("c"), counter("d")), (1, 0))
        values.set_tag("player", self.ivan.pk, "other")                             # всё ещё верно — не повторяется
        self.assertEqual(counter("c"), 1)
        values.set_tag("player", self.ivan.pk, "vip", False)
        self.assertEqual((counter("c"), counter("d")), (1, 1))

    def test_a_world_condition_by_wire(self):
        make([node("g", "ent:tag", owner="world", name="alarm"), node("w", "while", scope="world"), node("t", "do:world_count", name="c")],
             [wire("g", "on", "w", "f:condition"), wire("w", "true", "t")])
        values.set_tag("world", 0, "alarm")
        self.assertEqual(counter("c"), 1)

    def test_an_action_with_a_condition_does_and_undoes(self):
        core = Machine.objects.create(name="Core", hostname="core")
        make([node("g", "ent:tag", owner="world", name="lockdown"), node("a", "act:machine.status", variant="maintenance", host="core", text="locked")],
             [wire("g", "on", "a")])
        values.set_tag("world", 0, "lockdown")
        core.refresh_from_db()
        self.assertEqual(core.status, Machine.Status.MAINTENANCE)
        values.set_tag("world", 0, "lockdown", False)
        core.refresh_from_db()
        self.assertEqual(core.status, Machine.Status.ONLINE)

    def test_a_moment_lasts_while_the_condition_holds(self):
        from world import moments

        WorldMoment.objects.create(name="storm", schedule="once 2031-03-01 21:00", duration=600)
        make([node("g", "ent:count", owner="world", name="wind"), node("n", "number", value=5), node("c", "compare", op="ge"),
              node("a", "act:moment", variant="start", moment="storm")],
             [wire("g", "value", "c", "f:a"), wire("n", "value", "c", "f:b"), wire("c", "value", "a")])
        values.add("world", 0, "wind", 3)
        self.assertFalse(moments.running(WorldMoment.objects.get(name="storm")))
        values.add("world", 0, "wind", 4)
        self.assertTrue(moments.running(WorldMoment.objects.get(name="storm")))
        values.add("world", 0, "wind", -5)
        runtime.tick(force=True)
        self.assertFalse(moments.running(WorldMoment.objects.get(name="storm")))
