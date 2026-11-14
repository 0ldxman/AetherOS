"""Ноды сущностей и «Файлы игрока»."""
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from characters.models import Character
from filesystem.machine_view import view_for
from filesystem.testing import make_file
from graph import check, runtime
from graph.runtime import Doc, value_of
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


def one(type, run=None, **data):
    doc = Doc({"nodes": [{"id": "e", "type": type, "data": data}]})
    return lambda out: value_of(run, doc, "e", out)


class EntityTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.core = Machine.objects.create(name="Core", hostname="core")

    def test_machine_properties_and_lookup_by_name(self):
        get = one("ent:machine", machine="core")
        self.assertEqual((get("value"), get("name"), get("up")), ("core", "Core", True))
        self.core.halted = True
        self.core.save()
        self.assertFalse(get("up"))
        self.assertEqual(one("ent:machine", machine="CORE")("host"), "core")
        self.assertEqual(one("ent:machine", machine="core-x")("value"), "")
        self.assertFalse(one("ent:machine")("up"))

    def test_character_and_player(self):
        Character.objects.create(code="K7A", name="Kate")
        get = one("ent:character", character="kate")
        self.assertEqual((get("value"), get("callsign"), get("active")), ("K7A", "Kate", True))
        run = SimpleNamespace(user=self.ivan, state={})
        self.assertEqual(one("ent:player", run)("name"), "ivan")
        self.assertEqual(one("ent:player", run, player="nobody")("name"), "")

    def test_entity_feeds_an_action_and_text_finds_a_thing(self):
        graph = make([node("m", "manual"), node("t", "text", value="Core"), node("e", "ent:machine"), node("a", "do:world_flag")],
                     [wire("m", "fire", "a"), f("t", "value", "e", "machine"), f("e", "host", "a", "name")])
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m")
        from engine import values

        self.assertTrue(values.on("world", 0, "core"))

    def test_entity_type_is_checked(self):
        graph = make([node("c", "ent:character"), node("e", "ent:machine")], [f("c", "value", "e", "machine")])
        self.assertIn("«Машина» ждёт машину, а приходит персонажа", [p["text"] for p in check.problems(graph.doc)])


class PlayerFilesTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.core = Machine.objects.create(name="Core", hostname="core")
        MachineProfile.objects.create(machine=self.core, user=self.ivan, name="Ivan", login="ivan", freq=1)
        self.note = make_file(self.core, "/home/ivan/note.txt", body="hello").item
        self.run = SimpleNamespace(user=self.ivan, state={})

    def get(self, out, **data):
        return one("files", self.run, item=self.note.slug, **data)(out)

    def test_found_by_object_after_move(self):
        self.assertEqual((self.get("has"), self.get("where"), self.get("count")), (True, "core:/home/ivan/note.txt", 1))
        view_for(self.core, self.ivan, login="ivan").move("/home/ivan/note.txt", "/home/ivan/old.txt")
        self.assertEqual(self.get("where"), "core:/home/ivan/old.txt")
        self.assertEqual(self.get("count", machine="core"), 1)
        self.assertEqual(self.get("count", machine="other"), 0)

    def test_trash_and_edit(self):
        view = view_for(self.core, self.ivan, login="ivan")
        view.copy("/home/ivan/note.txt", "/home/ivan/copy.txt")
        self.assertEqual(self.get("count"), 2)
        view.move("/home/ivan/note.txt", "/home/ivan/.trash/note.txt")
        row = view_for(self.core, self.ivan, login="ivan").get("/home/ivan/.trash/note.txt").player
        row.trashed_at = timezone.now()
        row.save()
        self.assertEqual((self.get("count"), self.get("trash"), self.get("edited")), (1, True, False))
        view_for(self.core, self.ivan, login="ivan").put_item("/home/ivan/copy.txt", self.note, content="changed")
        self.assertTrue(self.get("edited"))

    def test_other_player_has_nothing(self):
        petr = get_user_model().objects.create_user("petr")
        self.assertFalse(one("files", SimpleNamespace(user=petr, state={}), item=self.note.slug)("has"))
        self.assertTrue(one("files", None, item=self.note.slug, player="ivan")("has"))


class TagCountTests(TestCase):
    def setUp(self):
        from engine import values

        self.values = values
        self.ivan = get_user_model().objects.create_user("ivan")
        self.olga = get_user_model().objects.create_user("olga")
        self.core = Machine.objects.create(name="Core", hostname="core")
        self.run = SimpleNamespace(user=self.ivan, state={})

    def test_actions_write_and_nodes_read(self):
        graph = make([node("m", "manual"), node("e", "ent:machine", machine="core"),
                      node("t", "do:tag", owner="machine", scope="player", name="hacked"),
                      node("c", "do:count", owner="world", name="alarm", delta=2),
                      node("p", "do:count", owner="player", mode="set", name="hints", value=5)],
                     [wire("m", "fire", "t"), wire("m", "fire", "c"), wire("m", "fire", "p"), f("e", "value", "t", "machine")])
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        v = self.values
        self.assertTrue(v.on("machine", self.core.pk, "hacked", self.ivan))
        self.assertFalse(v.on("machine", self.core.pk, "hacked"))
        self.assertEqual(v.get("count", "world", 0, "alarm"), 2)
        self.assertEqual(v.get("count", "player", self.ivan.pk, "hints"), 5)
        self.assertTrue(one("ent:tag", self.run, owner="machine", machine="core", scope="player", name="hacked")("on"))
        self.assertFalse(one("ent:tag", SimpleNamespace(user=self.olga, state={}), owner="machine", machine="core", scope="player",
                             name="hacked")("on"))
        self.assertTrue(one("ent:tag", None, owner="machine", machine="core", scope="player", **{"for": "ivan"}, name="hacked")("on"))
        self.assertEqual(one("ent:count", self.run, owner="player", name="hints")("value"), 5)
        v.describe("count", "world", "alarm", labels={"2": "Тревога"})
        self.assertEqual(one("ent:count", None, owner="world", name="alarm")("caption"), "Тревога")
        self.assertEqual(one("ent:count", None, owner="machine", machine="nowhere", name="x")("value"), 0)

    def test_old_kinds_are_hidden_but_still_work(self):
        from graph import nodes

        kinds = {k["name"]: k for k in nodes.catalog()["kinds"]}
        self.assertTrue(kinds["do:flag"]["hidden"] and kinds["read"]["hidden"])
        self.assertFalse(kinds["do:tag"]["hidden"])
        self.assertIn({"field": "for", "mode": "scope", "values": ["player"]}, kinds["ent:tag"]["when"])
