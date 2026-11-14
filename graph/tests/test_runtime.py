"""Исполнитель сценариев: старты, ожидания, ход, действия, время."""
from engine import values as store
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine.events import emit
from engine.models import Event
from graph import runtime, stats
from graph.models import Graph, Hit, Mark, Run, Start, Wait


def node(node_id, kind, **data):
    return {"id": node_id, "type": kind, "x": 0, "y": 0, "data": data}


def wire(src, out, dst, inp="in"):
    return {"from": src, "out": out, "to": dst, "in": inp}


def make(nodes, wires, active=True, slug="g"):
    graph = Graph.objects.create(slug=slug, title=slug, active=active, doc={"nodes": nodes, "wires": wires})
    runtime.rebuild_starts(graph)
    return graph


def counter(name="c"):
    return store.get("count", "world", 0, name)


class StartTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")

    def login_graph(self, **start):
        return make([node("m", "machine", host="archive", **start), node("a", "do:world_count", name="c")], [wire("m", "login", "a")])

    def test_event_starts_run_and_runs_action(self):
        graph = self.login_graph()
        self.assertEqual(Start.objects.filter(graph=graph).get().event, "machine.login")
        emit("machine.login", self.ivan, machine="archive", login="guest")
        self.assertEqual(counter(), 1)
        run = Run.objects.get()
        self.assertEqual((run.user, run.status, run.ctx["host"]), (self.ivan, Run.Status.DONE, "archive"))

    def test_other_machine_does_not_start(self):
        self.login_graph()
        emit("machine.login", self.ivan, machine="dock", login="guest")
        self.assertEqual(counter(), 0)

    def test_once_per_player_by_default(self):
        self.login_graph()
        for _ in range(2):
            emit("machine.login", self.ivan, machine="archive")
        emit("machine.login", self.anna, machine="archive")
        self.assertEqual(counter(), 2)

    def test_repeat_always(self):
        self.login_graph(repeat="always")
        for _ in range(3):
            emit("machine.login", self.ivan, machine="archive")
        self.assertEqual(counter(), 3)

    def test_inactive_graph_does_nothing(self):
        graph = self.login_graph()
        Graph.objects.filter(pk=graph.pk).update(active=False)
        emit("machine.login", self.ivan, machine="archive")
        self.assertEqual(counter(), 0)

    def test_player_flag_action_emits_event_for_next_graph(self):
        make([node("m", "machine", host="archive"), node("f", "do:flag", name="met")], [wire("m", "login", "f")], slug="one")
        make([node("n", "flag", name="met"), node("a", "do:world_flag", name="door")], [wire("n", "set", "a")], slug="two")
        emit("machine.login", self.ivan, machine="archive")
        self.assertTrue(store.on("player", self.ivan.pk, "met"))
        self.assertTrue(store.on("world", 0, "door"))
        self.assertTrue(Event.objects.filter(name="flag.set", user=self.ivan).exists())

    def test_ref_wire_feeds_action_field(self):
        make([node("m", "manual"), node("w", "world_flag", name="alarm"), node("a", "do:world_flag")],
             [wire("m", "fire", "a"), wire("w", "ref", "a", "f:name")])
        graph = Graph.objects.get()
        runtime.start_manual(graph, "m")
        self.assertTrue(store.on("world", 0, "alarm"))

    def test_account_action_without_machine_goes_to_fail(self):
        make([node("m", "manual"), node("k", "do:key", slug="boreas"), node("a", "do:world_count", name="c")], [wire("m", "fire", "k"), wire("k", "fail", "a")])
        runtime.start_manual(Graph.objects.get(), "m", self.ivan)
        self.assertEqual(counter(), 1)


class WaitTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.anna = get_user_model().objects.create_user("anna")

    def test_noun_with_input_waits_for_players_event(self):
        graph = make([node("m", "manual"), node("f", "file", item="report"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "read", "a")])
        run = runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(run.status, Run.Status.RUNNING)
        emit("file.read", self.anna, path="/r.txt", item="report")          # чужое событие не будит
        self.assertEqual(counter(), 0)
        emit("file.read", self.ivan, path="/r.txt", item="report")
        self.assertEqual(counter(), 1)
        self.assertFalse(Wait.objects.exists())
        self.assertEqual(Run.objects.get().status, Run.Status.DONE)

    def test_past_event_counts(self):
        emit("file.read", self.ivan, path="/r.txt", item="report")
        graph = make([node("m", "manual"), node("f", "file", item="report", past=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "read", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(counter(), 1)

    def test_anyone(self):
        graph = make([node("m", "manual"), node("f", "flag", name="x", anyone=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "set", "a")])
        runtime.start_manual(graph, "m")                                    # прохождение мира
        emit("flag.set", self.anna, flag="x")
        self.assertEqual(counter(), 1)

    def test_timeout_of_noun(self):
        graph = make([node("m", "manual"), node("f", "flag", name="x", timeout=10), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "timeout", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(Wait.objects.count(), 1)                           # выход «set» не подключён: ждём только срок
        Wait.objects.update(until=timezone.now() - timedelta(seconds=1))
        runtime.tick(force=True)
        self.assertEqual(counter(), 1)

    def test_wait_delay_then_tick(self):
        graph = make([node("m", "manual"), node("w", "wait", minutes=5, real=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), wire("w", "next", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        wait = Wait.objects.get()
        self.assertGreater(wait.until, timezone.now() + timedelta(minutes=4))
        runtime.tick(force=True)
        self.assertEqual(counter(), 0)
        Wait.objects.update(until=timezone.now() - timedelta(seconds=1))
        runtime.tick(force=True)
        self.assertEqual(counter(), 1)

    def test_wait_condition_wakes_on_players_event(self):
        graph = make([node("m", "manual"), node("w", "wait", mode="condition", condition="flag:ready"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), wire("w", "next", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(counter(), 0)
        store.set_tag("player", self.ivan.pk, "ready")
        emit("file.read", self.ivan, path="/x")
        self.assertEqual(counter(), 1)

    def test_race_cancels_other_branch(self):
        graph = make([node("m", "manual"), node("f1", "flag", name="a"), node("f2", "flag", name="b"), node("r", "race", count=2),
                      node("x", "do:world_count", name="c"), node("y", "do:world_count", name="d")],
                     [wire("m", "fire", "f1"), wire("m", "fire", "f2"), wire("f1", "set", "r", "i1"), wire("f2", "set", "r", "i2"),
                      wire("r", "o1", "x"), wire("r", "o2", "y")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(Wait.objects.count(), 2)
        emit("flag.set", self.ivan, flag="b")
        self.assertEqual((counter("c"), counter("d")), (0, 1))
        self.assertFalse(Wait.objects.exists())
        self.assertEqual(Run.objects.get().status, Run.Status.DONE)

    def test_all_joins_in_any_order(self):
        graph = make([node("m", "manual"), node("f1", "flag", name="a"), node("f2", "flag", name="b"), node("j", "all", count=2),
                      node("x", "do:world_count", name="c")],
                     [wire("m", "fire", "f1"), wire("m", "fire", "f2"), wire("f1", "set", "j", "i1"), wire("f2", "set", "j", "i2"), wire("j", "next", "x")])
        runtime.start_manual(graph, "m", self.ivan)
        emit("flag.set", self.ivan, flag="b")
        self.assertEqual(counter(), 0)
        emit("flag.set", self.ivan, flag="a")
        self.assertEqual(counter(), 1)

    def test_end_closes_run_and_waits(self):
        graph = make([node("m", "manual"), node("f", "flag", name="a"), node("e", "end", outcome="failed")],
                     [wire("m", "fire", "f"), wire("m", "fire", "e")])
        run = runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual((run.status, run.outcome), (Run.Status.DONE, "failed"))
        self.assertFalse(Wait.objects.exists())


class FlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.players = [User.objects.create_user(f"p{n}") for n in range(3)]

    def test_check_and_choose(self):
        graph = make([node("m", "manual"), node("c", "check", condition="flag:x"), node("yes", "do:world_count", name="yes"),
                      node("no", "do:world_count", name="no"),
                      node("s", "choose", rows=[{"label": "A", "condition": "flag:a"}, {"label": "X", "condition": "flag:x"}]),
                      node("r2", "do:world_count", name="r2"), node("else", "do:world_count", name="else")],
                     [wire("m", "fire", "c"), wire("c", "yes", "yes"), wire("c", "no", "no"), wire("m", "fire", "s"), wire("s", "r2", "r2"),
                      wire("s", "else", "else")])
        ivan = self.players[0]
        runtime.start_manual(graph, "m", ivan)
        store.set_tag("player", ivan.pk, "x")
        runtime.start_manual(graph, "m", ivan)
        self.assertEqual([counter(n) for n in ("yes", "no", "r2", "else")], [1, 1, 1, 1])

    def test_turns_round_robin(self):
        graph = make([node("m", "manual"), node("t", "turns", count=2), node("a", "do:world_count", name="a"), node("b", "do:world_count", name="b")],
                     [wire("m", "fire", "t"), wire("t", "b1", "a"), wire("t", "b2", "b")])
        for player in self.players:
            runtime.start_manual(graph, "m", player)
        self.assertEqual((counter("a"), counter("b")), (2, 1))

    def test_first_in_world_and_once(self):
        graph = make([node("m", "manual"), node("f", "first", count=1), node("w", "do:world_count", name="win"), node("l", "do:world_count", name="late"),
                      node("o", "once"), node("n", "do:world_count", name="new"), node("g", "do:world_count", name="again")],
                     [wire("m", "fire", "f"), wire("f", "pass", "w"), wire("f", "late", "l"), wire("m", "fire", "o"), wire("o", "pass", "n"),
                      wire("o", "again", "g")])
        first, second = self.players[:2]
        runtime.start_manual(graph, "m", first)
        runtime.start_manual(graph, "m", second)
        runtime.start_manual(graph, "m", second)
        self.assertEqual([counter(n) for n in ("win", "late", "new", "again")], [1, 2, 2, 1])

    def test_random_respects_zero_weight(self):
        graph = make([node("m", "manual"), node("r", "random", branches=[0, 1]), node("a", "do:world_count", name="a"), node("b", "do:world_count", name="b")],
                     [wire("m", "fire", "r"), wire("r", "b1", "a"), wire("r", "b2", "b")])
        for _ in range(4):
            runtime.start_manual(graph, "m", self.players[0])
        self.assertEqual((counter("a"), counter("b")), (0, 4))

    def test_cycle_without_wait_stops(self):
        graph = make([node("m", "manual"), node("a", "reroute"), node("b", "reroute")], [wire("m", "fire", "a"), wire("a", "next", "b"), wire("b", "next", "a")])
        run = runtime.start_manual(graph, "m")
        self.assertEqual((run.status, run.outcome), (Run.Status.DONE, "aborted"))

    def test_loop_through_wait(self):
        graph = make([node("m", "manual"), node("w", "wait", minutes=1, real=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), wire("w", "next", "a"), wire("a", "next", "w")])
        runtime.start_manual(graph, "m")
        for _ in range(3):
            Wait.objects.update(until=timezone.now() - timedelta(seconds=1))
            runtime.tick(force=True)
        self.assertEqual(counter(), 3)
        self.assertEqual(Wait.objects.count(), 1)

    def test_muted_action_passes_flow_through(self):
        graph = make([node("m", "manual"), {**node("x", "do:world_count", name="skip"), "mute": True}, node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "x"), wire("x", "next", "a")])
        runtime.start_manual(graph, "m")
        self.assertEqual((counter("skip"), counter("c")), (0, 1))

    def test_stats(self):
        graph = make([node("m", "manual"), node("s", "stage", title="x"), node("f", "flag", name="q"), node("r", "reroute")],
                     [wire("m", "fire", "s"), wire("s", "next", "f"), wire("f", "set", "r")])
        for player in self.players[:2]:
            runtime.start_manual(graph, "m", player)
        found = stats.of(graph)
        self.assertEqual(found["nodes"]["s"]["players"], 2)
        self.assertEqual(found["nodes"]["f"]["waiting"], 2)
        self.assertEqual(found["running"], 2)
        self.assertEqual(len(stats.waiting(graph, "f")), 2)


class TimeTests(TestCase):
    def test_daily_start_fires_once_per_day_and_not_on_enable(self):
        from machines.world import chrono

        game = chrono.game_now()
        at = (game - timedelta(minutes=1)).strftime("%H:%M")
        graph = make([node("t", "time", at=at), node("a", "do:world_count", name="c")], [wire("t", "fire", "a")])
        runtime.tick(force=True)
        self.assertEqual(counter(), 0)                                       # включили после срока: сегодня не догоняем
        Mark.objects.filter(graph=graph).update(value=0 + 1)
        runtime.tick(force=True)
        runtime.tick(force=True)
        self.assertEqual(counter(), 1)


class HookTests(TestCase):
    def test_events_of_world_reach_graphs(self):
        from world import state

        make([node("w", "counter", name="frag", threshold=2), node("a", "do:world_flag", name="open")], [wire("w", "reached", "a")])
        state.count("frag")
        self.assertFalse(store.on("world", 0, "open"))
        state.count("frag")
        self.assertTrue(store.on("world", 0, "open"))
        self.assertTrue(Hit.objects.exists())

    @mock.patch("graph.runtime.dispatch", side_effect=RuntimeError("boom"))
    def test_broken_graph_does_not_break_emit(self, _):
        self.assertIsNotNone(emit("file.read", None, path="/x"))


class CharacterEventTests(TestCase):
    def test_wrote_starts_character_noun(self):
        from characters import inbox
        from characters.models import Character

        mira = Character.objects.create(code="MIR", name="Mira")
        make([node("c", "character", character="MIR", text="*help*"), node("a", "do:world_count", name="c")], [wire("c", "air", "a")])
        ivan = get_user_model().objects.create_user("ivan")
        inbox._wrote(ivan, mira, "forum", "please HELP me")
        self.assertEqual(counter(), 0)                                       # другой канал
        inbox._wrote(ivan, mira, "air", "please HELP me")
        self.assertEqual(counter(), 1)
