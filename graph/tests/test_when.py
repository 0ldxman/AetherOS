"""Ноды «Когда…»: события по пространствам, фильтры, теги и счётчики любых владельцев, время."""
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from graph import check, runtime
from graph.models import Run
from graph.tests.test_runtime import counter, make, node, wire
from machines.models import Machine


class WhenTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")
        self.core = Machine.objects.create(name="Core", hostname="core")

    def one(self, kind, out, **data):
        return make([node("w", kind, **data), node("a", "do:world_count", name="c")], [wire("w", out, "a")])

    def test_machine_status_any_or_one(self):
        self.one("on:machine.status", "stopped")
        make([node("w", "on:machine.status", machine="other"), node("a", "do:world_count", name="d")], [wire("w", "stopped", "a")], slug="g2")
        emit("machine.stopped", None, machine="core")
        emit("machine.started", None, machine="core")
        self.assertEqual((counter("c"), counter("d")), (1, 0))

    def test_terminal_command_globs(self):
        self.one("on:terminal.command", "run", command="decrypt", args="*vault*")
        emit("command.run", self.ivan, machine="core", login="ivan", command="decrypt", args="/srv/VAULT.bin")
        emit("command.run", self.ivan, machine="core", login="ivan", command="decrypt", args="/srv/other")
        self.assertEqual(counter(), 1)

    def test_object_events_and_their_details(self):
        graph = make([node("w", "on:object.viewed", item="note"), node("a", "do:world_flag")],
                     [wire("w", "viewed", "a"), wire("w", "path", "a", "f:name")])
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        emit("file.read", self.ivan, machine="core", login="ivan", path="other", item="x")
        emit("file.read", self.ivan, machine="core", login="ivan", path="seen-it", item="note")
        self.assertTrue(values.on("world", 0, "seen-it"))

    def test_object_event_gives_the_placement(self):
        make([node("w", "on:object.viewed"), node("p", "ent:placement"), node("a", "act:tag", variant="on", owner="world")],
             [wire("w", "viewed", "a"), wire("w", "placement", "p", "f:placement"), wire("p", "name", "a", "f:name")])
        emit("file.read", self.ivan, machine="core", login="ivan", path="/home/report.txt", item="x")
        self.assertTrue(values.on("world", 0, "report.txt"))

    def test_object_got_by_source(self):
        self.one("on:object.got", "got", via="join")
        emit("object.got", self.ivan, item="k", path="/x", via="key")
        emit("object.got", self.ivan, item="k", path="/x", via="join")
        self.assertEqual(counter(), 1)

    def test_player_mail_only_mail_channel(self):
        self.one("on:player.mail", "sent", text="*пароль*")
        emit("character.wrote", self.ivan, character="K7A", channel="air", text="какой пароль")
        emit("character.wrote", self.ivan, character="K7A", channel="mail", text="какой ПАРОЛЬ?")
        self.assertEqual(counter(), 1)

    def test_tag_of_a_thing_for_a_player_wakes_only_them(self):
        graph = make([node("m", "manual"), node("w", "on:tag", owner="machine", machine="core", scope="player", name="hacked", own=True),
                      node("a", "do:world_count", name="c")], [wire("m", "fire", "w"), wire("w", "set", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        runtime.start_manual(graph, "m", self.anna)
        values.set_tag("machine", self.core.pk, "hacked", user=self.anna)
        values.set_tag("machine", self.core.pk, "hacked")                     # общий тег — другое значение
        self.assertEqual(counter(), 1)
        self.assertEqual(Run.objects.filter(user=self.anna, status="done").count(), 1)

    def test_shared_tag_wakes_everyone(self):
        graph = make([node("m", "manual"), node("w", "on:tag", owner="world", name="storm"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), wire("w", "set", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        runtime.start_manual(graph, "m", self.anna)
        values.set_tag("world", 0, "storm")
        self.assertEqual(counter(), 2)

    def test_counter_threshold_both_ways(self):
        make([node("w", "on:count.threshold", owner="player", name="hints", threshold=3, repeat="always"), node("u", "do:world_count", name="up"),
              node("d", "do:world_count", name="down")], [wire("w", "up", "u"), wire("w", "down", "d")])
        values.add("player", self.ivan.pk, "hints", 2)
        values.add("player", self.ivan.pk, "hints", 2)     # 2 -> 4: дошёл
        values.add("player", self.ivan.pk, "hints", 1)     # 5: уже выше
        values.put("player", self.ivan.pk, "hints", 1)     # 5 -> 1: ушёл ниже
        self.assertEqual((counter("up"), counter("down")), (1, 1))

    def test_schedule_targets(self):
        game = datetime(2031, 5, 14, 12, 7, tzinfo=dt_timezone.utc)            # среда
        self.assertEqual(runtime._time_target({"mode": "every", "minutes": 30}, game, "on:schedule"), game.replace(minute=0))
        self.assertEqual(runtime._time_target({"mode": "daily", "at": "21:00"}, game, "on:schedule"), datetime(2031, 5, 13, 21, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(runtime._time_target({"mode": "weekly", "at": "09:00", "days": "пн, пт"}, game, "on:schedule"),
                         datetime(2031, 5, 12, 9, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(runtime._time_target({"date": "2031-06-01", "at": "10:30"}, game, "on:time"), datetime(2031, 6, 1, 10, 30, tzinfo=dt_timezone.utc))

    def test_catalog_groups_new_nodes_and_hides_old_nouns(self):
        from graph import nodes

        kinds = {k["name"]: k for k in nodes.catalog()["kinds"]}
        self.assertEqual(kinds["on:machine.status"]["label"], "Машина: Статус изменён")
        self.assertFalse({"file", "machine", "flag", "time"} & set(kinds))
        self.assertFalse(kinds["manual"]["hidden"] or kinds["signal"]["hidden"])
        self.assertEqual(kinds["on:schedule"]["title"], "mode")

    def test_player_edit_and_key_arrival_are_events(self):
        from engine.models import Event
        from filesystem import keystore
        from filesystem.machine_view import view_for
        from filesystem.models import Item
        from filesystem.testing import make_file
        from machines.models import MachineProfile

        MachineProfile.objects.create(machine=self.core, user=self.ivan, name="Ivan", login="ivan", freq=1)
        note = make_file(self.core, "/home/ivan/note.txt", body="hello").item
        view = view_for(self.core, self.ivan, login="ivan")
        view.edit_text("/home/ivan/note.txt", "answer")
        changed = Event.objects.get(name="file.changed")
        self.assertEqual((changed.user, changed.data["item"], changed.data["path"]), (self.ivan, note.slug, "/home/ivan/note.txt"))
        key = Item.objects.create(slug="boreas", name="boreas", format="key")
        keystore.put(view, self.core, "ivan", key)
        got = Event.objects.get(name="object.got")
        self.assertEqual((got.data["item"], got.data["via"]), ("boreas", "key"))
