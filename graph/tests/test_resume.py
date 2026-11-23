"""Продолжение потока: событие из его же ноды не будит его посреди хода (иначе состояние затирается)."""
from django.test import TestCase

from engine import values
from graph.runtime import start_manual
from graph.tests.test_runtime import make, node, wire


class NestedResumeTests(TestCase):
    def test_an_event_from_the_same_flow_wakes_it_after_the_step_is_saved(self):
        # Кнопка → ждём тег t  ┐
        #        → ставим тег t ┴→ «Слияние: Все» → счётчик. Тег ставится в том же ходу, где поток встал ждать.
        graph = make([node("m", "manual"), node("w", "on:tag", owner="world", name="t"), node("a", "act:tag", variant="on", owner="world", name="t"),
                      node("j", "join", mode="all", count=3), node("c", "do:world_count", name="done")],
                     [wire("m", "fire", "w"), wire("m", "fire", "a"), wire("w", "set", "j", "i1"), wire("a", "next", "j", "i2"), wire("j", "next", "c")],
                     slug="nested")
        start_manual(graph, "m")
        self.assertTrue(values.on("world", 0, "t"))
        self.assertEqual(values.get(values.COUNT, "world", 0, "done"), 1)                # оба входа слияния дошли


class DependentStartsTests(TestCase):
    def test_saving_a_nested_scenario_rebuilds_the_graphs_that_use_it(self):
        from unittest import mock

        from graph import runtime

        inner = make([node("in", "group_in", sockets=[{"id": "go", "name": "go"}])], [], slug="inner")
        outer = make([node("s", "scenario", graph="inner")], [], slug="outer")
        make([node("x", "manual")], [], slug="alone")
        with mock.patch.object(runtime, "rebuild_starts") as rebuilt:
            runtime.rebuild_dependents(inner)
        self.assertEqual([call.args[0].slug for call in rebuilt.call_args_list], [outer.slug])     # только те, кто вкладывает


class CharacterFailureTests(TestCase):
    def test_a_reply_that_was_not_delivered_goes_to_fail(self):
        from graph.runtime import _delivered
        from characters.models import Reply
        from characters.outbox import OutboxError
        from types import SimpleNamespace

        with self.assertRaises(OutboxError):
            _delivered(SimpleNamespace(status=Reply.Status.FAILED, error="нет ящика"))
        self.assertIsNone(_delivered(None))
