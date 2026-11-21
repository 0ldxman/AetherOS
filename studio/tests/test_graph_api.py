"""Сценарии-графы в Студии: каталог, сохранение с проверкой, счётчики, кто ждёт, запуск вручную."""
from engine import values as store
from django.contrib.auth import get_user_model
from django.test import TestCase

from graph.models import Graph, Start
from team.testing import full_role

URL = "/studio/api/world/graphs"


def doc():
    return {"nodes": [{"id": "m", "type": "manual", "x": 0, "y": 0, "data": {}},
                      {"id": "f", "type": "on:tag", "x": 200, "y": 0, "data": {"owner": "player", "name": "met"}},
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
        self.assertIn("try:machine", names)
        self.assertIn("do:world_flag", names)
        self.assertIn("bool", data["types"])
        file = next(k for k in data["kinds"] if k["name"] == "on:placement.opened")
        self.assertIn({"name": "placement", "label": "Размещение", "type": "placement"}, file["outs"])

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
        self.assertIn({"node": "f", "text": "не заполнено «Имя»", "level": "error"}, data["problems"])

    def test_broken_doc_and_duplicate_slug(self):
        self.assertEqual(self.create(doc={"nodes": [{"id": "a"}, {"id": "a"}]}).status_code, 400)
        self.create()
        self.assertEqual(self.create().status_code, 400)

    def test_manual_start_stats_and_waiting(self):
        graph_id = self.create(active=True).json()["id"]
        response = self.client.post(f"{URL}/{graph_id}/control", {"node": "m", "player": self.ivan.pk}, content_type="application/json")
        self.assertEqual(response.json()["status"], "running")
        self.assertTrue(store.on("world", 0, "door"))
        found = self.client.get(f"{URL}/{graph_id}/stats").json()
        self.assertEqual(found["running"], 1)
        self.assertEqual(found["nodes"]["f"]["waiting"], 1)
        waiting = self.client.get(f"{URL}/{graph_id}/waiting/f").json()
        self.assertEqual(waiting[0]["player"], "ivan")
        self.assertEqual(self.client.post(f"{URL}/{graph_id}/control", {"node": "f"}, content_type="application/json").status_code, 400)

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


class PanelApiTests(TestCase):
    """Страница «Мир»: карточки сценариев, пульт (управление), сброс, включение."""

    def setUp(self):
        User = get_user_model()
        self.boss = User.objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.client.force_login(self.boss)
        nodes = [{"id": "sw", "type": "ctl_switch", "x": 0, "y": 0, "data": {"name": "Alarm"}},
                 {"id": "ch", "type": "ctl_choice", "x": 0, "y": 100, "data": {"name": "Mode", "options": "calm\nalert"}},
                 {"id": "nm", "type": "ctl_number", "x": 0, "y": 200, "data": {"name": "Level", "min": 0, "max": 10, "step": 2}},
                 {"id": "bt", "type": "manual", "x": 0, "y": 300, "data": {"name": "Go"}},
                 {"id": "st", "type": "stage", "x": 300, "y": 0, "data": {"title": "Door opened"}}]
        self.graph = Graph.objects.create(slug="panel", title="Panel", active=True, doc={"nodes": nodes, "wires": [{"from": "sw", "out": "on", "to": "st", "in": "in"}]})

    def card(self):
        return next(card for card in self.client.get(f"{URL}/panel").json() if card["slug"] == "panel")

    def post(self, path, body=None):
        return self.client.post(f"{URL}/{self.graph.pk}/{path}", body or {}, content_type="application/json")

    def test_card_lists_controls_stages_and_variables(self):
        card = self.card()
        self.assertEqual([(c["kind"], c["name"]) for c in card["controls"]], [("ctl_switch", "Alarm"), ("ctl_choice", "Mode"), ("ctl_number", "Level"), ("manual", "Go")])
        self.assertEqual(next(c for c in card["controls"] if c["kind"] == "ctl_number")["max"], 10)
        self.assertEqual(next(c for c in card["controls"] if c["kind"] == "ctl_choice")["options"], ["calm", "alert"])
        self.assertEqual((card["stages"][0]["title"], card["stages"][0]["hits"], card["variables"]), ("Door opened", 0, {}))
        self.assertEqual((card["errors"], card["waiting"], card["running"]), (0, 0, 0))

    def test_card_counts_errors_and_waiting_flows(self):
        from graph.runtime import start_control

        self.graph.doc["nodes"] += [{"id": "w", "type": "wait", "x": 400, "y": 0, "data": {"mode": "delay", "minutes": 5}},
                                    {"id": "bad", "type": "do:world_flag", "x": 500, "y": 0, "data": {}}]
        self.graph.doc["wires"] = [{"from": "bt", "out": "fire", "to": "w", "in": "in"}]
        self.graph.save()
        start_control(self.graph, "bt")
        card = self.card()
        self.assertEqual((card["waiting"], card["running"]), (1, 1))
        self.assertGreaterEqual(card["errors"], 1)

    def test_control_sets_value_and_counts_the_stage(self):
        self.assertEqual(self.post("control", {"node": "sw", "value": True}).status_code, 200)
        self.assertEqual(self.post("control", {"node": "ch", "value": "alert"}).status_code, 200)
        card = self.card()
        self.assertEqual(card["variables"], {"Alarm": True, "Mode": "alert"})
        self.assertEqual(next(c for c in card["controls"] if c["name"] == "Alarm")["value"], True)
        self.assertEqual(card["stages"][0]["hits"], 1)
        self.assertEqual(self.post("control", {"node": "ch", "value": "panic"}).status_code, 400)
        self.assertEqual(self.post("control", {"node": "nm", "value": 99}).status_code, 400)

    def test_reset_and_active(self):
        self.post("control", {"node": "sw", "value": True})
        self.assertEqual(self.post("reset").json()["variables"], {})
        self.assertEqual(self.post("active", {"active": False}).json(), {"active": False})
        self.graph.refresh_from_db()
        self.assertFalse(self.graph.active)
