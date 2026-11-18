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
        return make([node("m", "on:terminal.command", machine="archive", **start), node("a", "do:world_count", name="c")], [wire("m", "run", "a")])

    def test_event_starts_run_and_runs_action(self):
        graph = self.login_graph()
        self.assertEqual(Start.objects.filter(graph=graph).get().event, "command.run")
        emit("command.run", self.ivan, machine="archive", login="guest", command="login")
        self.assertEqual(counter(), 1)
        run = Run.objects.get()
        self.assertEqual((run.user, run.status, run.ctx["host"]), (self.ivan, Run.Status.DONE, "archive"))

    def test_other_machine_does_not_start(self):
        self.login_graph()
        emit("command.run", self.ivan, machine="dock", login="guest", command="login")
        self.assertEqual(counter(), 0)

    def test_once_per_player_by_default(self):
        self.login_graph()
        for _ in range(2):
            emit("command.run", self.ivan, machine="archive", command="login")
        emit("command.run", self.anna, machine="archive", command="login")
        self.assertEqual(counter(), 2)                                      # по разу на каждого игрока

    def test_once_per_game(self):
        self.login_graph(repeat="game")
        emit("command.run", self.ivan, machine="archive", command="login")
        emit("command.run", self.anna, machine="archive", command="login")
        self.assertEqual(counter(), 1)                                      # прохождение одно на всех: первый запустил

    def test_repeat_always(self):
        self.login_graph(repeat="always")
        for _ in range(3):
            emit("command.run", self.ivan, machine="archive", command="login")
        self.assertEqual(counter(), 3)

    def test_inactive_graph_does_nothing(self):
        graph = self.login_graph()
        Graph.objects.filter(pk=graph.pk).update(active=False)
        emit("command.run", self.ivan, machine="archive", command="login")
        self.assertEqual(counter(), 0)

    def test_player_flag_action_emits_event_for_next_graph(self):
        make([node("m", "on:terminal.command", machine="archive"), node("f", "do:flag", name="met")], [wire("m", "run", "f")], slug="one")
        make([node("n", "on:tag", owner="player", name="met"), node("a", "do:world_flag", name="door")], [wire("n", "set", "a")], slug="two")
        emit("command.run", self.ivan, machine="archive", command="login")
        self.assertTrue(store.on("player", self.ivan.pk, "met"))
        self.assertTrue(store.on("world", 0, "door"))
        self.assertTrue(Event.objects.filter(name="flag.set", user=self.ivan).exists())

    def test_ref_wire_feeds_action_field(self):
        make([node("m", "manual"), node("w", "text", value="alarm"), node("a", "do:world_flag")],
             [wire("m", "fire", "a"), wire("w", "value", "a", "f:name")])
        graph = Graph.objects.get()
        runtime.start_manual(graph, "m")
        self.assertTrue(store.on("world", 0, "alarm"))

    def test_account_action_without_machine_goes_to_fail(self):
        make([node("m", "manual"), node("k", "do:letter", item="boreas"), node("a", "do:world_count", name="c")], [wire("m", "fire", "k"), wire("k", "fail", "a")])
        runtime.start_manual(Graph.objects.get(), "m", self.ivan)
        self.assertEqual(counter(), 1)


class WaitTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.anna = get_user_model().objects.create_user("anna")

    def test_noun_with_input_waits_for_anyone_and_the_move_goes_on_with_them(self):
        graph = make([node("m", "manual"), node("f", "on:placement.opened", item="report"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "opened", "a")])
        run = runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(run.status, Run.Status.RUNNING)
        emit("file.read", self.anna, path="/r.txt", item="report")          # любой игрок двигает ход
        self.assertEqual(counter(), 1)
        self.assertFalse(Wait.objects.exists())
        run = Run.objects.get()
        self.assertEqual((run.status, run.user), (Run.Status.DONE, self.anna))

    def test_only_the_moves_player(self):
        graph = make([node("m", "manual"), node("f", "on:placement.opened", item="report", own=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "opened", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        emit("file.read", self.anna, path="/r.txt", item="report")          # «Только инициатор»: чужое не будит
        self.assertEqual(counter(), 0)
        emit("file.read", self.ivan, path="/r.txt", item="report")
        self.assertEqual(counter(), 1)

    def test_past_event_counts(self):
        emit("file.read", self.ivan, path="/r.txt", item="report")
        graph = make([node("m", "manual"), node("f", "on:placement.opened", item="report", past=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "opened", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(counter(), 1)

    def test_anyone(self):
        graph = make([node("m", "manual"), node("f", "on:tag", owner="player", name="x", anyone=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "f"), wire("f", "set", "a")])
        runtime.start_manual(graph, "m")                                    # прохождение мира
        store.set_tag("player", self.anna.pk, "x")
        self.assertEqual(counter(), 1)

    def test_timeout_of_noun(self):
        graph = make([node("m", "manual"), node("f", "on:tag", owner="player", name="x", timeout=10), node("a", "do:world_count", name="c")],
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

    def test_wait_adds_up_the_fields_and_takes_them_from_wires(self):
        graph = make([node("m", "manual"), node("w", "wait", real=True, days=1, hours=2, minutes=30, seconds=30), node("n", "number", value=3),
                      node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), wire("w", "next", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        span = (Wait.objects.get().until - timezone.now()).total_seconds()
        self.assertAlmostEqual(span, 86400 + 7200 + 1800 + 30, delta=5)
        from graph import check

        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        Wait.objects.all().delete()
        graph = make([node("m", "manual"), node("w", "wait", real=True), node("n", "number", value=3), node("a", "do:world_count", name="d")],
                     [wire("m", "fire", "w"), wire("w", "next", "a"), wire("n", "value", "w", "f:hours")], slug="wired")
        runtime.start_manual(graph, "m", self.ivan)
        self.assertAlmostEqual((Wait.objects.get().until - timezone.now()).total_seconds(), 3 * 3600, delta=5)

    def test_wait_until_a_date_and_the_title(self):
        from graph import nodes as N

        graph = make([node("m", "manual"), node("w", "wait", mode="until", at="2031-05-14 21:00", real=True), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), wire("w", "next", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(Wait.objects.get().until.strftime("%Y-%m-%d %H:%M"), "2031-05-14 21:00")
        kind = N.KINDS["wait"]
        self.assertEqual(N.wait_title({"mode": "until", "at": "2031-01-01 12:30"}), "Ждать до 2031-01-01 12:30")
        self.assertEqual([N.wait_title(d) for d in ({"minutes": 5}, {"minutes": 1}, {"hours": 1, "minutes": 30}, {"days": 2, "seconds": 21}, {})],
                         ["Ждать 5 минут", "Ждать 1 минуту", "Ждать 1 час 30 минут", "Ждать 2 дня 21 секунду", "Ждать"])
        self.assertEqual(N.titled(kind, {"minutes": 5}), "Ждать 5 минут")
        self.assertEqual(N.sockets(kind, {}, "out"), ["next"])

    def test_wait_condition_wakes_on_players_event_and_records_when(self):
        graph = make([node("m", "manual"), node("w", "wait_cond", condition="tag:ready"), node("a", "do:world_count", name="c"),
                      node("t", "text", value="{when}", subs=[{"id": "s1", "name": "when"}])],
                     [wire("m", "fire", "w"), wire("w", "next", "a"), wire("w", "when", "t", "s1")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual((counter(), Wait.objects.filter(kind=Wait.Kind.CONDITION).count()), (0, 1))
        store.set_tag("player", self.ivan.pk, "ready")
        emit("file.read", self.ivan, path="/x")
        self.assertEqual((counter(), Wait.objects.count()), (1, 0))
        vals = Run.objects.get().state["vals"]["w"]
        self.assertRegex(vals["when"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

    def test_wait_condition_passes_at_once_and_from_a_wire(self):
        store.set_tag("player", self.ivan.pk, "ready")
        graph = make([node("m", "manual"), node("w", "wait_cond", condition="tag:ready"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), wire("w", "next", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual((counter(), Wait.objects.count()), (1, 0))
        graph = make([node("m", "manual"), node("w", "wait_cond"), node("b", "boolean", value=False), node("a", "do:world_count", name="d")],
                     [wire("m", "fire", "w"), wire("w", "next", "a"), wire("b", "value", "w", "f:condition")], slug="wired")
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(counter("d"), 0)
        runtime.tick(force=True)                             # по таймеру: условие всё ещё ложно
        self.assertEqual(counter("d"), 0)

    def test_race_cancels_other_branch(self):
        graph = make([node("m", "manual"), node("f1", "on:tag", owner="player", name="a"), node("f2", "on:tag", owner="player", name="b"), node("r", "race", count=2),
                      node("x", "do:world_count", name="c"), node("y", "do:world_count", name="d")],
                     [wire("m", "fire", "f1"), wire("m", "fire", "f2"), wire("f1", "set", "r", "i1"), wire("f2", "set", "r", "i2"),
                      wire("r", "o1", "x"), wire("r", "o2", "y")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(Wait.objects.count(), 2)
        store.set_tag("player", self.ivan.pk, "b")
        self.assertEqual((counter("c"), counter("d")), (0, 1))
        self.assertFalse(Wait.objects.exists())
        self.assertEqual(Run.objects.get().status, Run.Status.DONE)

    def test_all_joins_in_any_order(self):
        graph = make([node("m", "manual"), node("f1", "on:tag", owner="player", name="a"), node("f2", "on:tag", owner="player", name="b"), node("j", "all", count=2),
                      node("x", "do:world_count", name="c")],
                     [wire("m", "fire", "f1"), wire("m", "fire", "f2"), wire("f1", "set", "j", "i1"), wire("f2", "set", "j", "i2"), wire("j", "next", "x")])
        runtime.start_manual(graph, "m", self.ivan)
        store.set_tag("player", self.ivan.pk, "b")
        self.assertEqual(counter(), 0)
        store.set_tag("player", self.ivan.pk, "a")
        self.assertEqual(counter(), 1)

    def test_end_closes_run_and_waits(self):
        graph = make([node("m", "manual"), node("f", "on:tag", owner="player", name="a"), node("e", "end", outcome="failed")],
                     [wire("m", "fire", "f"), wire("m", "fire", "e")])
        run = runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual((run.status, run.outcome), (Run.Status.DONE, "failed"))
        self.assertFalse(Wait.objects.exists())


class FlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.players = [User.objects.create_user(f"p{n}") for n in range(3)]

    def test_if(self):
        graph = make([node("m", "manual"), node("c", "check", condition="tag:x"), node("yes", "do:world_count", name="yes"),
                      node("no", "do:world_count", name="no")],
                     [wire("m", "fire", "c"), wire("c", "yes", "yes"), wire("c", "no", "no")])
        ivan = self.players[0]
        runtime.start_manual(graph, "m", ivan)
        store.set_tag("player", ivan.pk, "x")
        runtime.start_manual(graph, "m", ivan)
        self.assertEqual([counter(n) for n in ("yes", "no")], [1, 1])

    def test_turns_round_robin(self):
        graph = make([node("m", "manual"), node("t", "turns", count=2), node("a", "do:world_count", name="a"), node("b", "do:world_count", name="b")],
                     [wire("m", "fire", "t"), wire("t", "b1", "a"), wire("t", "b2", "b")])
        for player in self.players:
            runtime.start_manual(graph, "m", player)
        self.assertEqual((counter("a"), counter("b")), (2, 1))

    def test_first_in_world_and_once(self):
        graph = make([node("m", "manual"), node("f", "first", count=1), node("w", "do:world_count", name="win"), node("l", "do:world_count", name="late"),
                      node("o", "once"), node("n", "do:world_count", name="new"), node("g", "do:world_count", name="again"),
                      node("p", "once", per="player"), node("pn", "do:world_count", name="player_new")],
                     [wire("m", "fire", "f"), wire("f", "pass", "w"), wire("f", "late", "l"), wire("m", "fire", "o"), wire("o", "pass", "n"),
                      wire("o", "again", "g"), wire("m", "fire", "p"), wire("p", "pass", "pn")])
        first, second = self.players[:2]
        runtime.start_manual(graph, "m", first)
        runtime.start_manual(graph, "m", second)
        runtime.start_manual(graph, "m", second)
        self.assertEqual([counter(n) for n in ("win", "late", "new", "again", "player_new")], [1, 2, 1, 2, 2])

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
        graph = make([node("m", "manual"), node("s", "stage", title="x"), node("f", "on:tag", owner="player", name="q"), node("r", "reroute")],
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
        graph = make([node("t", "on:schedule", mode="daily", at=at), node("a", "do:world_count", name="c")], [wire("t", "fire", "a")])
        runtime.tick(force=True)
        self.assertEqual(counter(), 0)                                       # включили после срока: сегодня не догоняем
        Mark.objects.filter(graph=graph).update(value=0 + 1)
        runtime.tick(force=True)
        runtime.tick(force=True)
        self.assertEqual(counter(), 1)


class HookTests(TestCase):
    def test_events_of_world_reach_graphs(self):
        from world import state

        make([node("w", "on:count.threshold", owner="world", name="frag", threshold=2), node("a", "do:world_flag", name="open")], [wire("w", "up", "a")])
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
        make([node("c", "on:character.mail", character="MIR", text="*help*"), node("a", "do:world_count", name="c")], [wire("c", "sent", "a")])
        ivan = get_user_model().objects.create_user("ivan")
        inbox._wrote(ivan, mira, "air", "please HELP me")
        self.assertEqual(counter(), 0)                                       # другой канал
        inbox._wrote(ivan, mira, "mail", "please HELP me")
        self.assertEqual(counter(), 1)
