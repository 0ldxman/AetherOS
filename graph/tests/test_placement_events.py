"""События размещения: «Размещение: Изменено» (отредактировано, перемещено, удалено, восстановлено, удалено насовсем), «Открыто», «Появилось».

Изменение — «было там, стало здесь»: удаление переносит файл в корзину, возврат — из неё. Ждущая нода идёт за файлом.
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from engine import values
from engine.events import emit
from engine.models import Event
from graph import check, nodes, runtime
from graph.models import Run
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile
from filesystem.testing import make_app, make_file


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


class PlacementWhenTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.petr = get_user_model().objects.create_user("petr")
        Machine.objects.create(name="Core", hostname="core")

    def tag(self, name):
        return node(f"t-{name}", "act:tag", variant="on", owner="world", name=name)

    def test_object_filter_catches_any_file_of_the_object(self):
        make([node("w", "on:placement.opened", item="note"), self.tag("seen")], [wire("w", "opened", "t-seen")])
        emit("file.read", self.ivan, machine="core", login="ivan", path="/tmp/other.txt", item="memo")
        self.assertFalse(values.on("world", 0, "seen"))
        emit("file.read", self.ivan, machine="core", login="ivan", path="/home/renamed.txt", item="note")
        self.assertTrue(values.on("world", 0, "seen"))

    def test_one_file_of_one_player_each_change_its_output(self):
        self.assertEqual(nodes.KINDS["on:placement.changed"].covers, {"placement": ("item", "path", "machine")})
        make([node("w", "on:placement.changed", placement="ivan@core:/home/a.txt"), self.tag("gone"), self.tag("edited")],
             [wire("w", "deleted", "t-gone"), wire("w", "edited", "t-edited")])
        emit("file.deleted", self.petr, machine="core", login="petr", path="/home/a.txt", to="/home/petr/.trash/a.txt")
        emit("file.deleted", self.ivan, machine="core", login="ivan", path="/home/b.txt", to="/home/ivan/.trash/b.txt")
        self.assertFalse(values.on("world", 0, "gone"))
        emit("file.deleted", self.ivan, machine="CORE", login="ivan", path="/home/a.txt", to="/home/ivan/.trash/a.txt")
        self.assertEqual((values.on("world", 0, "gone"), values.on("world", 0, "edited")), (True, False))

    def test_was_and_now(self):
        make([node("w", "on:placement.changed", path="/home/*"), node("a", "ent:placement"), node("t", "act:tag", variant="on", owner="world")],
             [wire("w", "deleted", "t"), f("w", "from_placement", "a", "placement"), f("a", "name", "t", "name")])
        emit("file.deleted", self.ivan, machine="core", login="ivan", path="/home/a.txt", to="/home/ivan/.trash/a.txt")
        self.assertTrue(values.on("world", 0, "a.txt"))
        found = Run.objects.get().state["vals"]["w"]
        self.assertEqual((found["from_placement"], found["placement"]), ("ivan@core:/home/a.txt", "ivan@core:/home/ivan/.trash/a.txt"))

    def test_appeared_by_way(self):
        make([node("w", "on:placement.appeared", via="copied"), self.tag("copied")], [wire("w", "appeared", "t-copied")])
        emit("file.created", self.ivan, machine="core", login="ivan", path="/home/n.sig", via="created")
        self.assertFalse(values.on("world", 0, "copied"))
        emit("file.created", self.ivan, machine="core", login="ivan", path="/home/n2.txt", via="copied", **{"from": "/home/n.txt"})
        self.assertTrue(values.on("world", 0, "copied"))

    def test_old_object_events_are_hidden_but_work(self):
        self.assertTrue(nodes.KINDS["on:object.viewed"].hidden)
        self.assertFalse(nodes.KINDS["on:placement.changed"].hidden)
        doc = {"nodes": [node("w", "on:placement.changed"), self.tag("x")], "wires": [wire("w", "purged", "t-x")]}
        self.assertEqual([p for p in check.problems(doc) if p["level"] == "error"], [])


@override_settings(FORCE_SCRIPT_NAME=None)
class PlayerCommandTests(TestCase):
    """Команды терминала шлют события, а ждущая нода идёт за файлом."""

    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", icon="terminal", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1, mail="ivan@aether-main")
        for path in ("/home/a.txt", "/home/b.txt"):
            make_file(cls.main, path, state="")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def post(self, payload):
        return json.loads(self.client.post(reverse("terminal:execute"), data=json.dumps(payload), content_type="application/json").content)

    def run_command(self, text):
        data = self.post({"command": text})
        if data.get("prompt"):
            data = self.post({"answer": "y"})
        self.assertEqual(data["exit_code"], 0, data["output"])
        return data

    def events(self, name, *keys):
        return [tuple(e.data.get(k) for k in keys) for e in Event.objects.filter(name=name).order_by("pk")]

    def test_mv_cp_del_rcvr_wipe(self):
        self.run_command("mv /home/a.txt /home/c.txt")
        self.assertEqual(self.events("file.moved", "from", "path"), [("/home/a.txt", "/home/c.txt")])
        self.run_command("cp /home/c.txt /home/d.txt")
        self.assertEqual(self.events("file.created", "via", "from", "path"), [("copied", "/home/c.txt", "/home/d.txt")])
        self.run_command("del /home/b.txt")
        self.run_command("rcvr /home/ivan/.trash/b.txt /home/e.txt")
        self.assertEqual(self.events("file.deleted", "path", "to"), [("/home/b.txt", "/home/ivan/.trash/b.txt")])
        self.assertEqual(self.events("file.restored", "from", "path"), [("/home/ivan/.trash/b.txt", "/home/e.txt")])
        self.run_command("del /home/d.txt")
        self.run_command("wipe -f")
        self.assertEqual(self.events("file.purged", "path"), [("/home/ivan/.trash/d.txt",)])

    def test_waiting_node_follows_the_file_through_move_and_trash(self):
        graph = make([node("m", "manual"), node("p", "ent:placement", machine="aether-main", path="/home/a.txt"),
                      node("w", "on:placement.changed"), node("t", "act:tag", variant="on", owner="world", name="back")],
                     [wire("m", "fire", "w"), f("p", "value", "w", "placement"), wire("w", "restored", "t")])
        runtime.start_manual(graph, "m", self.user)
        self.run_command("mv /home/a.txt /home/renamed.txt")
        self.run_command("del /home/renamed.txt")                         # ждёт уже файл в корзине
        self.run_command("del /home/b.txt")
        self.run_command("rcvr /home/ivan/.trash/b.txt")
        self.assertFalse(values.on("world", 0, "back"))
        self.run_command("rcvr /home/ivan/.trash/renamed.txt")
        self.assertTrue(values.on("world", 0, "back"))
