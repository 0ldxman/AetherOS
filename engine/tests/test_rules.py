"""Правила на события: образец подробностей, условие на факты игрока, кратность и «кто первым»."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import rules
from engine.events import emit
from engine.models import Rule, RuleFire
from forum.models import Post, Section, Space
from mail.models import Flag
from team.testing import full_role
from world.models import WorldCounter, WorldFlag


class RuleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")

    def rule(self, **fields):
        values = {"name": "r", "on": "key.got", "match": {"slug": "boreas"}, "actions": [{"do": "world_count", "name": "decoded"}], "once": "player"}
        return Rule.objects.create(**{**values, **fields})

    def counter(self):
        found = WorldCounter.objects.filter(name="decoded").first()
        return found.value if found else 0

    def test_once_per_player(self):
        self.rule()
        emit("key.got", self.ivan, slug="boreas")
        emit("key.got", self.ivan, slug="boreas")
        emit("key.got", self.anna, slug="boreas")
        emit("key.got", self.anna, slug="mask")
        self.assertEqual(self.counter(), 2)

    def test_once_in_the_world_remembers_who_was_first(self):
        rule = self.rule(once="world")
        emit("key.got", self.anna, slug="boreas")
        emit("key.got", self.ivan, slug="boreas")
        self.assertEqual(self.counter(), 1)
        self.assertEqual(rules.first(rule)[0], self.anna)

    def test_always_and_wildcards(self):
        self.rule(on="file.read", match={"path": "/home/*/door.bin"}, once="always")
        emit("file.read", self.ivan, path="/home/ivan/door.bin")
        emit("file.read", self.ivan, path="/home/ivan/door.bin")
        emit("file.read", self.ivan, path="/home/ivan/other.bin")
        self.assertEqual(self.counter(), 2)

    def test_condition_on_player_facts(self):
        self.rule(condition="flag:met-guard")
        emit("key.got", self.ivan, slug="boreas")
        self.assertEqual(self.counter(), 0)
        self.assertFalse(RuleFire.objects.exists())               # не сработало: потом ещё может
        Flag.objects.create(user=self.ivan, name="met-guard")
        emit("key.got", self.ivan, slug="boreas")
        self.assertEqual(self.counter(), 1)

    def test_player_actions_and_the_chronicle_line(self):
        space = Space.objects.create(slug="net", title="Net")
        log = Section.objects.create(space=space, title="Chronicle", write="authors")
        self.rule(once="world", actions=[{"do": "flag", "name": "decoder"},
                                         {"do": "forum", "section": log.pk, "mode": "append", "title": "World log", "text": "{player} first decoded BOREAS"}])
        emit("key.got", self.ivan, slug="boreas")
        self.assertTrue(Flag.objects.filter(user=self.ivan, name="decoder").exists())
        self.assertIn("first decoded BOREAS", Post.objects.get().text)
        self.assertNotIn("{player}", Post.objects.get().text)

    def test_a_loop_of_rules_stops(self):
        Rule.objects.create(name="ping", on="world.flag", match={"flag": "a"}, once="always", actions=[{"do": "world_unflag", "name": "a"}, {"do": "world_flag", "name": "b"}])
        Rule.objects.create(name="pong", on="world.flag", match={"flag": "b"}, once="always", actions=[{"do": "world_unflag", "name": "b"}, {"do": "world_flag", "name": "a"}])
        emit("world.flag", self.ivan, flag="a", on=True)            # не зависает
        self.assertTrue(WorldFlag.objects.exists())


class RuleApiTests(TestCase):
    def setUp(self):
        self.boss = get_user_model().objects.create_user("boss", is_staff=True, role=full_role())
        self.client.force_login(self.boss)

    def post(self, body):
        return self.client.post("/studio/api/world/rules", body, content_type="application/json")

    def test_create_validate_and_see_who_fired(self):
        body = {"name": "first-boreas", "on": "key.got", "match": {"slug": "boreas"}, "condition_text": "flag:met", "once": "world",
                "actions": [{"do": "world_flag", "name": "decoded"}]}
        self.assertEqual(self.post({**body, "on": "nope"}).status_code, 400)
        self.assertEqual(self.post({**body, "match": {"nope": "x"}}).status_code, 400)
        self.assertEqual(self.post({**body, "actions": [{"do": "goto", "step": "x"}]}).status_code, 400)
        self.assertEqual(self.post({**body, "actions": [{"do": "alert", "message": "x"}]}).status_code, 400)       # браузера у правила нет
        response = self.post(body)
        self.assertEqual(response.status_code, 200)
        row = response.json()["rules"][0]
        self.assertEqual((row["condition_text"], row["fires"]), ("flag:met", 0))
        ivan = get_user_model().objects.create_user("ivan")
        Flag.objects.create(user=ivan, name="met")
        emit("key.got", ivan, slug="boreas")
        row = self.client.get("/studio/api/world/rules").json()["rules"][0]
        self.assertEqual((row["fires"], row["first_player"]), (1, "ivan"))
        self.client.post(f"/studio/api/world/rules/{row['id']}/reset")
        self.assertEqual(self.client.get("/studio/api/world/rules").json()["rules"][0]["fires"], 0)
