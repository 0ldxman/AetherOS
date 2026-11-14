"""Сценарии-графы в Студии: каталог, сохранение с проверкой, счётчики, кто ждёт, запуск вручную."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from graph.models import Graph, Start
from team.testing import full_role
from world.models import WorldFlag

URL = "/studio/api/world/graphs"


def doc():
    return {"nodes": [{"id": "m", "type": "manual", "x": 0, "y": 0, "data": {}},
                      {"id": "f", "type": "flag", "x": 200, "y": 0, "data": {"name": "met"}},
                      {"id": "r", "type": "reroute", "x": 300, "y": 0, "data": {}},
                      {"id": "a", "type": "do:world_flag", "x": 400, "y": 0, "data": {"name": "door"}}],
            "wires": [{"from": "m", "out": "fire", "to": "a", "in": "in"}, {"from": "m", "out": "fire", "to": "f", "in": "in"},
                      {"from": "f", "out": "set", "to": "r", "in": "in"}]}


class GraphApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.boss = User.objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.ivan = User.objects.create_user("ivan")
        self.client.force_login(self.boss)

    def create(self, **body):
        return self.client.post(URL, {"slug": "archive", "title": "Archive", "doc": doc(), **body}, content_type="application/json")

    def test_catalog(self):
        data = self.client.get(f"{URL}/catalog").json()
        names = [k["name"] for k in data["kinds"]]
        self.assertIn("machine", names)
        self.assertIn("do:world_flag", names)
        self.assertEqual(data["ref_kinds"]["key"], "item")

    def test_create_save_and_starts(self):
        response = self.create(active=True)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["problems"], [])
        graph = Graph.objects.get()
        self.assertEqual(list(Start.objects.filter(graph=graph).values_list("event", flat=True)), ["@manual"])     # стартует кнопкой
        rows = self.client.get(URL).json()
        self.assertEqual((rows[0]["nodes"], rows[0]["errors"]), (4, 0))

    def test_problems_are_returned_not_refused(self):
        bad = doc()
        bad["nodes"][1]["data"] = {}
        data = self.create(doc=bad).json()
        self.assertIn({"node": "f", "text": "не заполнено «Метка»", "level": "error"}, data["problems"])

    def test_broken_doc_and_duplicate_slug(self):
        self.assertEqual(self.create(doc={"nodes": [{"id": "a"}, {"id": "a"}]}).status_code, 400)
        self.create()
        self.assertEqual(self.create().status_code, 400)

    def test_manual_start_stats_and_waiting(self):
        graph_id = self.create(active=True).json()["id"]
        response = self.client.post(f"{URL}/{graph_id}/start", {"node": "m", "player": self.ivan.pk}, content_type="application/json")
        self.assertEqual(response.json()["status"], "running")
        self.assertTrue(WorldFlag.objects.get(name="door").on)
        found = self.client.get(f"{URL}/{graph_id}/stats").json()
        self.assertEqual(found["running"], 1)
        self.assertEqual(found["nodes"]["f"]["waiting"], 1)
        waiting = self.client.get(f"{URL}/{graph_id}/waiting/f").json()
        self.assertEqual(waiting[0]["player"], "ivan")
        self.assertEqual(self.client.post(f"{URL}/{graph_id}/start", {"node": "f"}, content_type="application/json").status_code, 400)

    def test_live_check(self):
        bad = doc()
        bad["nodes"][1]["data"] = {}
        found = self.client.post(f"{URL}/check", {"doc": bad}, content_type="application/json").json()
        self.assertEqual(found[0]["node"], "f")

    def test_update_and_delete(self):
        graph_id = self.create().json()["id"]
        response = self.client.put(f"{URL}/{graph_id}", {"slug": "archive", "title": "New", "doc": doc(), "active": True}, content_type="application/json")
        self.assertEqual(response.json()["title"], "New")
        self.assertEqual(self.client.delete(f"{URL}/{graph_id}").status_code, 204)
        self.assertFalse(Graph.objects.exists())

    def test_needs_world_rights(self):
        author = get_user_model().objects.create_user("author", password="pw", is_staff=True)
        self.client.force_login(author)
        self.assertEqual(self.create().status_code, 403)
