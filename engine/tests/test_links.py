"""Карта связей: что требуется и где это взять; разрывы загадок."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import links
from engine.models import Rule
from filesystem.models import Item, ItemKey
from filesystem.testing import key_item
from forum.models import Section, Space
from team.testing import full_role
from world.models import WorldFlag, WorldMoment, WorldTrigger


def row(kind, name):
    return next((r for r in links.analyze() if (r.kind, r.name) == (kind, name)), None)


class LinksTests(TestCase):
    def setUp(self):
        self.space = Space.objects.create(slug="net", title="Net")

    def test_a_key_required_but_nowhere_to_get_is_a_break(self):
        key_item("mask")
        Section.objects.create(space=self.space, title="Inner", read_if="mask")
        found = row("key", "mask")
        self.assertEqual((found.level, [p.what for p in found.required]), ("error", ["раздел форума"]))
        Rule.objects.create(name="give-mask", on="machine.login", actions=[{"do": "key", "slug": "mask"}])
        self.assertEqual(row("key", "mask").level, "ok")

    def test_hidden_keys_count_as_a_source_and_unused_ones_are_noted(self):
        key = key_item("alpha")
        ItemKey.objects.create(item=Item.objects.create(slug="note", name="note.txt", format="txt"), key=key)
        found = row("key", "alpha")
        self.assertEqual((found.level, found.granted[0].what), ("info", "спрятан в файле"))

    def test_a_key_missing_from_the_registry(self):
        Section.objects.create(space=self.space, title="Inner", read_if="ghost")
        self.assertEqual(row("key", "ghost").problem, "такого ключа нет в реестре")

    def test_player_flags_from_actions(self):
        Rule.objects.create(name="door", on="file.read", condition="flag:met-guard", actions=[])
        self.assertEqual(row("flag", "met-guard").level, "error")
        Rule.objects.create(name="meet", on="mail.sent", actions=[{"do": "flag", "name": "met-guard"}])
        self.assertEqual(row("flag", "met-guard").level, "ok")

    def test_world_flags_from_moments_or_only_by_hand(self):
        WorldTrigger.objects.create(name="t", condition={"all": ["world:uplink", "world:sealed"]}, actions=[])
        WorldMoment.objects.create(name="uplink", schedule="daily 21:00")
        WorldFlag.objects.create(name="sealed")
        self.assertEqual(row("world", "uplink").level, "ok")
        self.assertEqual((row("world", "sealed").level, row("world", "sealed").problem), ("warning", "ставится только вручную на пульте"))

    def test_the_studio_lists_links(self):
        boss = get_user_model().objects.create_user("boss", is_staff=True, role=full_role())
        self.client.force_login(boss)
        Section.objects.create(space=self.space, title="Inner", read_if="flag:x")
        data = self.client.get("/studio/api/engine/links").json()
        self.assertEqual((data[0]["kind"], data[0]["name"], data[0]["level"]), ("flag", "x", "error"))
