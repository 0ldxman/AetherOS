"""Действия этапа 3: экран игрока через очередь, счётчик игрока, теги персонажа, файлы, машины, учётки, сеть, моменты."""
from engine import values as store
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine import actions as engine
from engine import facts, push
from engine.context import Ctx
from engine.events import emit
from engine.models import Event
from filesystem.testing import key_item
from machines.models import AccountBlock, Machine, MachineProfile, NetNode, NetResource, Session
from machines.network import bridge
from machines.world import power
from mail.boxes import Box
from secure.access import satisfied
from world.models import WorldEvent


def run(actions, **ctx):
    return engine.run(actions, Ctx(source="test", **ctx))


class ScreenTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan", password="pw")

    def test_screen_actions_queue_effects_and_desktop_takes_them_once(self):
        run([{"do": "notify", "title": "INCOMING", "text": "hi"}, {"do": "windows", "message": "x", "count": 99},
             {"do": "ticker", "text": "run"}, {"do": "terminal_text", "text": "root: hi"}], user=self.ivan)
        taken = push.take(self.ivan)
        self.assertEqual([t["op"] for t in taken], ["notify", "alert", "ticker", "terminal"])
        self.assertEqual(taken[1]["count"], 40)
        self.assertEqual(push.take(self.ivan), [])

    def test_an_effect_for_an_account_waits_until_the_desk_is_there(self):
        from machines.models import Machine, MachineProfile

        core = Machine.objects.create(name="Core", hostname="core")
        guard = MachineProfile.objects.create(machine=core, login="guard", name="guard", freq=1)
        home = MachineProfile.objects.create(machine=core, login="ivan", name="ivan", freq=2)
        push.send(self.ivan, "notify", push.where_of(guard), title="for guard")
        push.send(self.ivan, "terminal", push.where_of(machine=core), text="for core terminal")
        push.send(self.ivan, "ticker", text="anywhere")
        self.assertEqual([t["op"] for t in push.take(self.ivan, desk=home, terminal=None)], ["ticker"])        # стол не на guard
        self.assertEqual([t["op"] for t in push.take(self.ivan, desk=guard, terminal=home)], ["notify", "terminal"])
        self.assertEqual(push.take(self.ivan, desk=guard, terminal=home), [])

    def test_stale_effects_are_dropped(self):
        push.send(self.ivan, "notify", title="old")
        from engine.models import Push

        Push.objects.update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(push.take(self.ivan), [])

    def test_desktop_endpoint(self):
        push.send(self.ivan, "notify", title="x")
        self.client.force_login(self.ivan)
        self.assertEqual(self.client.get("/desktop/push/").json()["items"][0]["op"], "notify")

    def test_unknown_scene_is_reported(self):
        self.assertTrue(engine.check([{"do": "scene", "scene": "nope"}], provides=("world", "user")))


class PlayerFactsTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_player_counter_and_condition(self):
        run([{"do": "player_count", "name": "hints"}, {"do": "player_count", "name": "hints", "delta": 2}], user=self.ivan)
        self.assertEqual(store.get("count", "player", self.ivan.pk, "hints"), 3)
        known = facts.of(self.ivan)
        self.assertTrue(satisfied("count:hints>=3", known))
        self.assertFalse(satisfied("count:hints>3", known))
        self.assertTrue(satisfied("count:hints", known))
        self.assertFalse(satisfied("count:other", known))
        run([{"do": "player_count", "name": "hints", "mode": "set", "value": 0}], user=self.ivan)
        self.assertFalse(satisfied("count:hints", facts.of(self.ivan)))
        self.assertEqual(Event.objects.filter(name="player.counter").count(), 3)

    def test_character_tags(self):
        from characters.models import Character

        Character.objects.create(code="MIR", name="Mira")
        run([{"do": "character_tag", "character": "mir", "tag": "Exposed"}])
        self.assertTrue(satisfied("tag:character:MIR:exposed", frozenset()))
        run([{"do": "character_tag", "character": "MIR", "tag": "exposed", "mode": "remove"}])
        self.assertFalse(satisfied("tag:character:MIR:exposed", frozenset()))

    def test_condition_syntax_accepts_new_atoms(self):
        from documents.markup.expr import parse_expr

        self.assertEqual(parse_expr("count:hints>=2 and tag:character:MIR:exposed"), {"all": ["count:hints>=2", "tag:character:MIR:exposed"]})
        self.assertFalse(facts.is_key("count:x"))


class FileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        cls.ivan = get_user_model().objects.create_user("ivan")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, user=cls.ivan, name="Ivan", login="ivan", freq=1)

    def box(self):
        return Box.of_profile(self.profile, self.ivan)

    def test_delete_move_replace(self):
        a, b = key_item("alpha"), key_item("beta")
        self.box().view.put_item("/home/a.key", a)
        run([{"do": "file_change", "path": "/home/a.key", "mode": "replace", "item": "beta"}], user=self.ivan, box=self.box())
        self.assertEqual(self.box().view.get("/home/a.key").item, b)
        run([{"do": "file_change", "path": "/home/a.key", "mode": "move", "target": "/home/b.key"}], user=self.ivan, box=self.box())
        self.assertFalse(self.box().view.exists("/home/a.key"))
        self.assertTrue(self.box().view.exists("/home/b.key"))
        run([{"do": "file_delete", "path": "/home/b.key"}], user=self.ivan, box=self.box())
        self.assertFalse(self.box().view.exists("/home/b.key"))
        run([{"do": "file_delete", "path": "/home/none"}], user=self.ivan, box=self.box())
        self.assertTrue(WorldEvent.objects.filter(text__contains="нет файла").exists())


class MachineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Archive", hostname="archive")
        cls.ivan = get_user_model().objects.create_user("ivan")
        cls.anna = get_user_model().objects.create_user("anna")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, name="Guest", login="guest", freq=2)

    def test_stop_hides_host_and_kicks_sessions(self):
        Session.objects.create(user=self.ivan, profile=self.profile)
        run([{"do": "machine_power", "host": "archive", "state": "stop"}])
        self.assertEqual(bridge.resolve("archive", "guest").error, "no_host")
        self.assertTrue(Session.objects.filter(kick_at__isnull=False).exists())
        self.assertTrue(Event.objects.filter(name="machine.stopped", host="archive").exists())
        run([{"do": "machine_power", "host": "archive", "state": "start"}])
        self.assertFalse(bridge.resolve("archive", "guest").error)
        self.assertTrue(Event.objects.filter(name="machine.started").exists())

    def test_maintenance_closes_entry_but_not_the_session(self):
        Session.objects.create(user=self.ivan, profile=self.profile)
        run([{"do": "machine_power", "host": "archive", "state": "maintenance", "text": "back at 18:00"}])
        machine = Machine.objects.get(pk=self.machine.pk)
        self.assertEqual((bridge.resolve("archive", "guest").error, power.maintenance_text(machine)), ("maintenance", "back at 18:00"))
        self.assertFalse(Session.objects.filter(kick_at__isnull=False).exists())          # кто внутри — остаётся
        self.assertFalse(power.is_down(machine))                                          # в сети
        self.assertTrue(Event.objects.filter(name="machine.maintenance.started", host="archive").exists())
        run([{"do": "machine_power", "host": "archive", "state": "start"}])
        self.assertFalse(bridge.resolve("archive", "guest").error)
        self.assertTrue(Event.objects.filter(name="machine.maintenance.ended").exists())

    def test_reboot_comes_back_by_itself(self):
        run([{"do": "machine_power", "host": "archive", "state": "reboot", "minutes": 5}])
        self.assertTrue(power.is_down(Machine.objects.get(pk=self.machine.pk)))
        Machine.objects.filter(pk=self.machine.pk).update(halted_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(power.tick(force=True), 1)
        self.assertFalse(Machine.objects.get(pk=self.machine.pk).halted)

    def test_account_block_for_player_and_for_all(self):
        run([{"do": "account", "host": "archive", "login": "guest", "block": 10}], user=self.ivan)
        self.assertGreater(bridge.locked_for(self.ivan, self.profile), 0)
        self.assertEqual(bridge.locked_for(self.anna, self.profile), 0)
        run([{"do": "account", "host": "archive", "login": "guest", "scope": "all", "block": 10}])
        self.assertGreater(bridge.locked_for(self.anna, self.profile), 0)
        run([{"do": "account", "host": "archive", "login": "guest", "scope": "all", "unblock": True}])
        self.assertEqual(bridge.locked_for(self.anna, self.profile), 0)
        self.assertEqual(AccountBlock.objects.count(), 1)

    def test_password_for_all_only(self):
        from django.contrib.auth.hashers import check_password

        run([{"do": "account", "host": "archive", "login": "guest", "password": "x"}], user=self.ivan)
        self.assertTrue(WorldEvent.objects.filter(text__contains="только для всех").exists())
        run([{"do": "account", "host": "archive", "login": "guest", "scope": "all", "password": "x7k2"}])
        self.assertTrue(check_password("x7k2", MachineProfile.objects.get(pk=self.profile.pk).password_hash))

    def test_net_node(self):
        resource = NetResource.objects.create(address="apollo.com")
        node = NetNode.objects.create(resource=resource, path="info", response="old")
        run([{"do": "net_node", "address": "apollo.com", "path": "info", "token": "s", "response": "new"}])
        node.refresh_from_db()
        self.assertEqual((node.token, node.response), ("s", "new"))
        run([{"do": "net_node", "address": "apollo.com", "token": "-"}])

    def test_moments(self):
        from world.models import WorldMoment

        WorldMoment.objects.create(name="storm", duration=30)
        run([{"do": "moment_start", "moment": "storm"}])
        self.assertTrue(store.on("world", 0, "storm"))
        run([{"do": "moment_end", "moment": "storm"}])
        self.assertFalse(store.on("world", 0, "storm"))


class GraphEventTests(TestCase):
    def test_global_event_wakes_every_player(self):
        from graph import runtime
        from graph.tests.test_runtime import counter, make, node, wire
        from world import state

        User = get_user_model()
        players = [User.objects.create_user(f"p{n}") for n in range(2)]
        graph = make([node("m", "manual"), node("w", "on:tag", owner="world", name="alarm"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), wire("w", "set", "a")])
        for player in players:
            runtime.start_manual(graph, "m", player)
        state.set_flag("alarm", True, "test", players[0])
        self.assertEqual(counter(), 2)

    def test_command_event_only_when_heard(self):
        from engine import events

        events._heard["at"] = 0
        self.assertFalse(events.heard("command.run"))
        from graph.tests.test_runtime import make, node, wire

        make([node("c", "on:terminal.command", command="decrypt"), node("a", "do:world_count", name="c")], [wire("c", "run", "a")])
        events._heard["at"] = 0
        self.assertTrue(events.heard("command.run"))
        emit("command.run", get_user_model().objects.create_user("ivan"), command="decrypt", args="x")
        from graph.tests.test_runtime import counter

        self.assertEqual(counter(), 1)
