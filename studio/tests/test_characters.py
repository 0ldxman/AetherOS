"""Персонажи в Студии: карточка, код, каналы, кто ведёт; голос персонажа на форуме."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from air.models import Station
from characters.models import Character
from forum.models import Section, Space
from mail.models import Persona
from team.testing import full_role


class CharactersStudioTests(TestCase):
    def setUp(self):
        self.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.client.force_login(self.boss)

    def call(self, method, path, body=None):
        response = getattr(self.client, method)(f"/studio/api/characters{path}", data=json.dumps(body) if body is not None else None, content_type="application/json")
        return response.status_code, (response.json() if response.content else None)

    def test_create_with_generated_code_and_channels(self):
        persona = Persona.objects.create(address="op7@core.relay")
        station = Station.objects.create(name="OPERATOR-7", kind="character")
        status, made = self.call("post", "", {"name": "Operator 7", "callsign": "operator-7", "personas": [persona.pk], "stations": [station.pk],
                                              "voice": "short, never says please", "owner_id": self.boss.pk})
        self.assertEqual(status, 200)
        self.assertEqual((made["code"], made["callsign"], made["mail"], made["air"], made["owner"]), ("OP7", "OPERATOR-7", ["op7@core.relay"], ["OPERATOR-7"], "boss"))
        status, made = self.call("put", f"/{made['id']}", {"name": "Operator 7", "code": "OP7", "personas": [], "stations": [station.pk]})
        self.assertEqual(made["mail"], [])
        self.assertIsNone(Persona.objects.get(pk=persona.pk).character)

    def test_validation(self):
        Character.objects.create(code="OP7", name="Other", callsign="OPERATOR-7")
        status, data = self.call("post", "", {"name": "", "code": "op7", "callsign": "operator-7", "status": "alive"})
        self.assertEqual(status, 400)
        self.assertEqual(set(data["fields"]), {"name", "code", "callsign", "status"})
        player = get_user_model().objects.create_user("player")
        self.assertIn("owner_id", self.call("post", "", {"name": "X", "owner_id": player.pk})[1]["fields"])

    def test_options_list_free_and_taken_channels(self):
        mine = Character.objects.create(code="OP7", name="Operator")
        Persona.objects.create(address="a@x", character=mine)
        Persona.objects.create(address="b@x")
        data = self.call("get", "/options")[1]
        self.assertEqual([(p["label"], p["character"]) for p in data["personas"]], [("a@x", mine.pk), ("b@x", None)])
        self.assertIn("boss", [a["username"] for a in data["authors"]])

    def test_forum_voice_uses_the_character(self):
        found = Character.objects.create(code="OP7", name="Operator 7", callsign="OPERATOR-7", color=2)
        section = Section.objects.create(space=Space.objects.create(slug="net", title="Net"), title="General")
        response = self.client.post("/studio/api/forum/topics", data=json.dumps({"section": section.pk, "title": "Hi", "text": "t", "character": found.pk}),
                                    content_type="application/json")
        post = response.json()["posts"][0]
        self.assertEqual((post["name"], post["kind"]), ("OPERATOR-7", "character"))
        response = self.client.post("/studio/api/forum/topics", data=json.dumps({"section": section.pk, "title": "Hi", "text": "t"}), content_type="application/json")
        self.assertEqual(response.status_code, 400)


    def test_station_is_created_on_the_character(self):
        Character.objects.create(code="OP7", name="Operator 7")
        found = Character.objects.get()
        status, data = self.call("post", f"/{found.pk}/stations", {"name": "operator-7"})
        self.assertEqual((status, data["air"], data["callsign"]), (200, ["OPERATOR-7"], "OPERATOR-7"))
        self.assertEqual(Station.objects.get().character, found)
        self.assertIn("station", self.call("post", f"/{found.pk}/stations", {"name": "OPERATOR-7"})[1]["fields"])
        self.assertIn("station", self.call("post", f"/{found.pk}/stations", {"name": "7up"})[1]["fields"])

    def test_inbox_by_channel_and_status(self):
        from characters.models import Inbound

        found = Character.objects.create(code="OP7", name="Operator 7")
        a = Inbound.objects.create(character=found, channel="mail", sender="ivan@main", subject="hi", text="are you there")
        Inbound.objects.create(character=found, channel="air", sender="IVAN", text="OPERATOR-7?")
        self.assertEqual(self.call("get", f"/{found.pk}")[1]["inbox"], {"mail": 1, "forum": 0, "air": 1})
        rows = self.call("get", f"/{found.pk}/inbox?channel=mail")[1]
        self.assertEqual([r["subject"] for r in rows], ["hi"])
        status, row = self.call("post", f"/inbox/{a.pk}/status", {"status": "taken"})
        self.assertEqual((row["status"], row["taken_by"]), ("taken", "boss"))
        self.call("post", f"/inbox/{a.pk}/status", {"status": "answered"})
        self.assertEqual(self.call("get", f"/{found.pk}/inbox?channel=mail")[1], [])
        self.assertEqual(len(self.call("get", f"/{found.pk}/inbox?channel=mail&status=all")[1]), 1)
        self.assertEqual(self.call("post", f"/inbox/{a.pk}/status", {"status": "lost"})[0], 400)


    def test_answer_from_the_inbox_context_and_journal(self):
        from characters.models import Inbound

        found = Character.objects.create(code="OP7", name="Operator 7")
        Station.objects.create(name="OPERATOR-7", kind="character", character=found)
        player = get_user_model().objects.create_user("ivan")
        row = Inbound.objects.create(character=found, channel="air", user=player, sender="IVAN", text="OPERATOR-7?", ref={"freq": "14.230"})
        status, reply = self.call("post", f"/inbox/{row.pk}/answer", {"text": "QSL", "delay": 20, "actions": [{"do": "flag", "name": "met"}]})
        self.assertEqual((status, reply["status"], reply["author"], reply["player"]), (200, "pending", "boss", "ivan"))
        context = self.call("get", f"/inbox/{row.pk}/context")[1]
        self.assertEqual((context["player"]["username"], [h["kind"] for h in context["history"]], len(context["replies"])), ("ivan", ["in", "out"], 1))
        self.assertEqual(context["stations"][0]["label"], "OPERATOR-7")
        self.assertEqual([r["id"] for r in self.call("get", f"/{found.pk}/replies")[1]], [reply["id"]])
        status, cancelled = self.call("post", f"/replies/{reply['id']}/cancel")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.call("post", f"/replies/{reply['id']}/cancel")[0], 400)
        status, data = self.call("post", f"/inbox/{row.pk}/answer", {"text": " "})
        self.assertEqual((status, list(data["fields"])), (400, ["text"]))
