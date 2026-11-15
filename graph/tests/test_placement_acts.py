"""«Размещение: Изменить» и «Размещение: Создать / Добавить»: действия сценария с файлами игрока."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.models import Event
from filesystem.copies import at
from filesystem.machine_view import view_for
from filesystem.testing import make_file
from graph import check, runtime
from graph.models import Run
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


class PlacementActTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.main = Machine.objects.create(name="Main", hostname="main")
        MachineProfile.objects.create(machine=self.main, user=self.ivan, name="Ivan", login="ivan", freq=1)
        self.note = make_file(self.main, "/home/ivan/note.txt", body="hello").item
        make_file(self.main, "/home/ivan/b.txt", body="b")
        self.memo = make_file(self.main, "/srv/memo.txt", body="memo").item

    def act(self, variant, placement="ivan@main:/home/ivan/note.txt", **data):
        values.set_tag("world", 0, "ok", False)
        graph = make([node("m", "manual"), node("a", "act:placement", variant=variant, placement=placement, **data),
                      node("ok", "act:tag", variant="on", owner="world", name="ok")], [wire("m", "fire", "a"), wire("a", "next", "ok")],
                     slug=f"g{Run.objects.count()}")
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        run = Run.objects.order_by("-pk").first()
        return values.on("world", 0, "ok"), run.state["vals"]["a"]["placement"]

    def exists(self, path):
        found = at(self.ivan, self.main, path)
        return found is not None and not found.trashed

    def test_move_by_new_name_and_into_folder(self):
        self.assertEqual(self.act("move", target="renamed.txt"), (True, "ivan@main:/home/ivan/renamed.txt"))
        self.assertFalse(self.exists("/home/ivan/note.txt"))
        _, where = self.act("move", placement="ivan@main:/home/ivan/renamed.txt", target="/tmp/")
        self.assertEqual(where, "ivan@main:/tmp/renamed.txt")
        self.assertEqual(Event.objects.filter(name="file.moved").count(), 2)

    def test_trash_restore_purge(self):
        ok, where = self.act("trash")
        self.assertTrue(ok)
        self.assertTrue(where.startswith("ivan@main:/home/ivan/.trash/note.txt"), where)
        self.assertTrue(at(self.ivan, self.main, where.split(":", 1)[1]).trashed)
        _, back = self.act("restore", placement=where)
        self.assertEqual(back, "ivan@main:/home/ivan/note.txt")
        self.assertTrue(self.exists("/home/ivan/note.txt"))
        _, gone = self.act("purge")
        self.assertEqual(gone, "")
        self.assertIsNone(at(self.ivan, self.main, "/home/ivan/note.txt"))

    def test_replace_object(self):
        self.act("replace", item=self.memo.slug)
        self.assertEqual(at(self.ivan, self.main, "/home/ivan/note.txt").item, self.memo.slug)

    def test_list_in_list_out_and_failure(self):
        graph = make([node("m", "manual"), node("find", "find", path="/home/ivan/*.txt"), node("a", "act:placement", variant="trash"),
                      node("ok", "act:tag", variant="on", owner="world", name="ok"), node("bad", "act:tag", variant="on", owner="world", name="bad")],
                     [wire("m", "fire", "a"), f("find", "value", "a", "placement"), wire("a", "next", "ok"), wire("a", "fail", "bad")])
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(len(Run.objects.get().state["vals"]["a"]["placement"]), 2)
        self.assertTrue(values.on("world", 0, "ok"))
        self.assertFalse(self.exists("/home/ivan/b.txt"))
        self.assertFalse(self.act("move", placement="ivan@main:/nowhere.txt", target="x.txt")[0])

    def test_create_and_add(self):
        graph = make([node("m", "manual"), node("c", "act:placement.create", machine="main", path="/home/{login}/hint.txt", text="ping {login}"),
                      node("d", "act:placement.create", placement="ivan@main:/home/ivan/memo.txt", item=self.memo.slug)],
                     [wire("m", "fire", "c"), wire("c", "next", "d")])
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        view = view_for(self.main, self.ivan, login="ivan")
        self.assertIn("ping", view.get("/home/ivan/hint.txt").own_text or "")
        self.assertEqual(at(self.ivan, self.main, "/home/ivan/memo.txt").item, self.memo.slug)
        self.assertEqual(Event.objects.filter(name="file.created").count(), 1)
        self.assertEqual(Event.objects.filter(name="object.got").count(), 1)
