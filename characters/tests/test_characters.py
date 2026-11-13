"""Персонажи: код, цвет, каналы."""
from django.test import TestCase

from air.models import Station
from characters import logic
from characters.models import Character
from mail.models import Persona


class CharacterTests(TestCase):
    def test_code_from_name_and_collisions(self):
        self.assertEqual(logic.code_for("OPERATOR-7"), "OP7")
        self.assertEqual(logic.code_for("mapt"), "MAP")
        self.assertEqual(logic.code_for("Al"), "ALX")
        Character.objects.create(code="MAP", name="Map")
        self.assertEqual(logic.code_for("Mapper"), "MA0")

    def test_color_matches_the_forum_hash(self):
        self.assertIn(logic.color_for("OPERATOR-7"), range(logic.COLORS))
        self.assertEqual(logic.color_for(""), 0)

    def test_channels_of_a_character(self):
        found = Character.objects.create(code="OP7", name="Operator 7", callsign="OPERATOR-7")
        Persona.objects.create(address="op7@core.relay", character=found)
        Station.objects.create(name="OPERATOR-7", kind="character", character=found)
        self.assertEqual(logic.channels(found), {"mail": ["op7@core.relay"], "air": ["OPERATOR-7"]})
        self.assertEqual(found.signature, "OPERATOR-7")
