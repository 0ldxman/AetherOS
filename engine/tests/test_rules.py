"""Правила на события: образец подробностей, условие на факты игрока, кратность и «кто первым»."""
from engine import values as store
from engine.models import Value
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import rules
from engine.events import emit
from engine.models import Rule, RuleFire
from forum.models import Post, Section, Space


class RuleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")

    def rule(self, **fields):
        values = {"name": "r", "on": "key.got", "match": {"slug": "boreas"}, "actions": [{"do": "world_count", "name": "decoded"}], "once": "player"}
        return Rule.objects.create(**{**values, **fields})

    def counter(self):
        return store.get("count", "world", 0, "decoded")

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
        self.rule(condition="tag:met-guard")
        emit("key.got", self.ivan, slug="boreas")
        self.assertEqual(self.counter(), 0)
        self.assertFalse(RuleFire.objects.exists())               # не сработало: потом ещё может
        store.set_tag("player", self.ivan.pk, "met-guard")
        emit("key.got", self.ivan, slug="boreas")
        self.assertEqual(self.counter(), 1)

    def test_player_actions_and_the_chronicle_line(self):
        space = Space.objects.create(slug="net", title="Net")
        log = Section.objects.create(space=space, title="Chronicle", write="authors")
        self.rule(once="world", actions=[{"do": "flag", "name": "decoder"},
                                         {"do": "forum", "section": log.pk, "mode": "append", "title": "World log", "text": "{player} first decoded BOREAS"}])
        emit("key.got", self.ivan, slug="boreas")
        self.assertTrue(store.on("player", self.ivan.pk, "decoder"))
        self.assertIn("first decoded BOREAS", Post.objects.get().text)
        self.assertNotIn("{player}", Post.objects.get().text)

    def test_a_loop_of_rules_stops(self):
        Rule.objects.create(name="ping", on="world.flag", match={"flag": "a"}, once="always", actions=[{"do": "world_unflag", "name": "a"}, {"do": "world_flag", "name": "b"}])
        Rule.objects.create(name="pong", on="world.flag", match={"flag": "b"}, once="always", actions=[{"do": "world_unflag", "name": "b"}, {"do": "world_flag", "name": "a"}])
        emit("world.flag", self.ivan, flag="a", on=True)            # не зависает
        self.assertTrue(Value.objects.filter(kind="tag", owner="world").exists())
