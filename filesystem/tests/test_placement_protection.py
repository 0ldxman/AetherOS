"""Своя защита места: у файла с объектом место может заменить объектные условие и слои или снять их.

Запуск: python manage.py test filesystem.tests.test_placement_protection
"""
from django.core.exceptions import ValidationError
from django.test import TestCase

from filesystem.manager import filemanager
from filesystem.models import Item, Placement, Volume


class PlacementProtectionTests(TestCase):
    def setUp(self):
        volume = Volume.objects.create(slug="v")
        self.item = Item.objects.create(slug="doc", name="doc", format="txt", body="x", state="> corrupted", access="cardkey")
        self.place = Placement.objects.create(volume=volume, name="doc.txt", item=self.item)

    def save(self, **fields):
        data = {"access_mode": "inherit", "access": "", "state_mode": "inherit", "state": ""} | fields
        return filemanager.set_protection(self.place, data["access_mode"], data["access"], data["state_mode"], data["state"])

    def test_a_fresh_place_follows_its_item(self):
        self.assertEqual(filemanager.protection_of(self.place), {"access_mode": "inherit", "access": "", "state_mode": "inherit", "state": ""})

    def test_own_condition_and_layers_replace_the_items(self):
        self.save(access_mode="replace", access="a and (b or not c)", state_mode="replace", state="> encrypted pw attempts=2")
        self.place.refresh_from_db()
        self.assertEqual(self.place.access, {"all": ["a", {"any": ["b", {"not": "c"}]}]})
        self.assertEqual(filemanager.protection_of(self.place), {
            "access_mode": "replace", "access": "a and (b or not c)", "state_mode": "replace", "state": "> encrypted pw attempts=2",
        })

    def test_none_removes_the_protection_and_inherit_forgets_the_own_values(self):
        self.save(access_mode="replace", access="a", state_mode="replace", state="> corrupted")
        self.save(access_mode="none", state_mode="none")
        self.place.refresh_from_db()
        self.assertEqual((self.place.access_mode, self.place.access, self.place.state_mode, self.place.state), ("none", {}, "none", ""))
        self.save()
        self.place.refresh_from_db()
        self.assertEqual((self.place.access_mode, self.place.state_mode), ("inherit", "inherit"))

    def test_the_two_halves_are_independent(self):
        self.save(access_mode="replace", access="a", state_mode="inherit")
        self.place.refresh_from_db()
        self.assertEqual((self.place.access_mode, self.place.state_mode, self.place.state), ("replace", "inherit", ""))

    def test_wrong_input_is_named_by_field_and_nothing_is_saved(self):
        for fields, field in [
            ({"access_mode": "replace", "access": "a and"}, "access"),
            ({"access_mode": "replace", "access": ""}, "access"),
            ({"state_mode": "replace", "state": ""}, "state"),
            ({"state_mode": "replace", "state": "> no_such_layer"}, "state"),
            ({"access_mode": "sometimes"}, "access_mode"),
        ]:
            with self.assertRaises(ValidationError) as caught:
                self.save(**fields)
            self.assertIn(field, caught.exception.message_dict, fields)
        self.place.refresh_from_db()
        self.assertEqual((self.place.access_mode, self.place.state_mode), ("inherit", "inherit"))

    def test_a_file_with_its_own_text_is_refused(self):
        own = filemanager.new_text_file(self.place.volume, None, "own.txt", "text")
        with self.assertRaises(ValidationError):
            filemanager.set_protection(own, "replace", "a", "inherit", "")
