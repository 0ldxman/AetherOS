"""Теги и счётчики владельцев: общие и свои у игрока, переименование вещи, события мира и игрока, описание."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from characters.models import Character
from engine import values
from engine.models import Event
from machines.models import Machine
from world import state


class ValueTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.olga = get_user_model().objects.create_user("olga")
        self.core = Machine.objects.create(name="Core", hostname="core")

    def test_shared_and_per_player_are_separate(self):
        oid = values.owner_id("machine", "CORE")
        values.set_tag("machine", oid, "quarantine")
        values.set_tag("machine", oid, "hacked", user=self.ivan)
        self.assertTrue(values.on("machine", oid, "quarantine"))
        self.assertTrue(values.on("machine", oid, "hacked", self.ivan))
        self.assertFalse(values.on("machine", oid, "hacked"))
        self.assertFalse(values.on("machine", oid, "hacked", self.olga))

    def test_renaming_the_thing_keeps_its_values(self):
        oid = values.owner_id("machine", self.core)
        values.add("machine", oid, "alarm", 2)
        self.core.hostname = "core-2"
        self.core.save()
        self.assertEqual(values.get("count", "machine", values.owner_id("machine", "core-2"), "alarm"), 2)
        self.assertEqual(values.owner_key("machine", oid), "core-2")

    def test_counters_add_and_put(self):
        kate = Character.objects.create(code="K7A", name="Kate")
        self.assertEqual(values.add("character", kate.pk, "trust", 2, user=self.ivan), 2)
        self.assertEqual(values.add("character", kate.pk, "trust", -1, user=self.ivan), 1)
        self.assertEqual(values.put("character", kate.pk, "trust", 7, user=self.olga), 7)
        self.assertEqual(values.get("count", "character", kate.pk, "trust", self.ivan), 1)

    def test_world_and_player_changes_keep_their_events(self):
        values.set_tag("world", 0, "storm")
        self.assertIn("storm", state.snapshot()["flags"])
        values.set_tag("player", self.ivan.pk, "met", actor=self.ivan)
        values.set_tag("player", self.ivan.pk, "met", actor=self.ivan)                  # уже стоит: ничего
        values.add("player", self.ivan.pk, "hints", 3, actor=self.ivan)
        names = list(Event.objects.order_by("pk").values_list("name", flat=True))
        self.assertEqual(names, ["world.flag", "flag.set", "player.counter"])
        self.assertEqual(Event.objects.get(name="flag.set").user, self.ivan)

    def test_names_and_info(self):
        with self.assertRaises(values.BadValue):
            values.check_name("bad:name")
        self.assertEqual(values.check_name(" Act-2 "), "act-2")
        values.describe("count", "world", "act", label="Акт", labels={"1": "Тишина", "2": "Архив", "x": "no"})
        self.assertEqual(values.info("count", "world", "act"), ("Акт", {"1": "Тишина", "2": "Архив"}))
        self.assertEqual(values.caption("count", "world", 0, "act", 2), "Архив")
        self.assertIsNone(values.owner_id("machine", "nowhere"))
        self.assertEqual(values.get("count", "machine", None, "x"), 0)
