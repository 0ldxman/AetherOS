"""Таблица провинций в Студии: всего изменений владения, последняя смена владельца и сортировка."""
import datetime as dt
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from map.models import Country, Ownership, Province
from team.testing import full_role

API = "/studio/api/map/provinces"


@override_settings(FORCE_SCRIPT_NAME=None)
class ProvinceTableTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))
        old = Country.objects.create(code="OLD", name="Old", color="#111111", valid_from=dt.date(1900, 1, 1))
        new = Country.objects.create(code="NEW", name="New", color="#222222", valid_from=dt.date(1900, 1, 1))
        self.a = Province.objects.create(code="A-1", source_code="t-a", name="Alpha")
        self.b = Province.objects.create(code="B-1", source_code="t-b", name="Beta")
        self.c = Province.objects.create(code="C-1", source_code="t-c", name="Gamma")
        Ownership.objects.create(province=self.a, country=old, date_from=dt.date(1900, 1, 1), de_jure=True, de_facto=True)
        Ownership.objects.create(province=self.a, country=new, date_from=dt.date(1940, 1, 1), de_jure=False, de_facto=True)
        Ownership.objects.create(province=self.b, country=old, date_from=dt.date(1950, 1, 1), de_jure=True, de_facto=False)

    def rows(self, **query):
        data = self.client.get(API, query).json()
        return {row["name"]: row for row in data["rows"]}, [row["name"] for row in data["rows"]]

    def test_total_changes_and_the_last_change_with_the_previous_owner(self):
        rows, _ = self.rows()
        self.assertEqual(rows["Alpha"]["records"], 2)
        change = rows["Alpha"]["last_change"]
        self.assertEqual((change["old"], change["new"], change["date"]), ("Old", "New", "1940-01-01"))
        self.assertEqual((change["de_jure"], change["de_facto"]), (False, True))
        first = rows["Beta"]["last_change"]
        self.assertIsNone(first["old"])
        self.assertEqual(first["new"], "Old")
        self.assertEqual(rows["Gamma"]["records"], 0)
        self.assertIsNone(rows["Gamma"]["last_change"])

    def test_the_last_change_is_counted_on_the_chosen_date(self):
        rows, _ = self.rows(on="1920-01-01")
        self.assertEqual(rows["Alpha"]["last_change"]["new"], "Old")
        self.assertIsNone(rows["Alpha"]["last_change"]["old"])
        self.assertIsNone(rows["Beta"]["last_change"])

    def test_sorting(self):
        self.assertEqual(self.rows(sort="name")[1], ["Alpha", "Beta", "Gamma"])
        self.assertEqual(self.rows(sort="-name")[1], ["Gamma", "Beta", "Alpha"])
        self.assertEqual(self.rows(sort="-records")[1][0], "Alpha")
        self.assertEqual(self.rows(sort="-last")[1][:2], ["Beta", "Alpha"])
        self.assertEqual(self.rows(sort="code")[1], ["Alpha", "Beta", "Gamma"])
        self.assertEqual(self.rows(sort="nonsense")[1], ["Alpha", "Beta", "Gamma"])
