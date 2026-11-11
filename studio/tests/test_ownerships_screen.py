"""Экран «Владения» в Студии: прежний владелец, проблемы, события (дата + страна-получатель), пачки."""
import datetime as dt
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from map.models import Country, Ownership, Province
from team.testing import full_role

API = "/studio/api/map/ownerships"


@override_settings(FORCE_SCRIPT_NAME=None)
class OwnershipScreenTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))
        self.old = Country.objects.create(code="OLD", name="Old", color="#111111", valid_from=dt.date(1900, 1, 1), valid_to=dt.date(1945, 1, 1))
        self.new = Country.objects.create(code="NEW", name="New", color="#222222", valid_from=dt.date(1930, 1, 1))
        self.p1 = Province.objects.create(code="P-1", source_code="s1", name="One")
        self.p2 = Province.objects.create(code="P-2", source_code="s2", name="Two")
        self.p3 = Province.objects.create(code="P-3", source_code="s3", name="Three")
        for p in (self.p1, self.p2, self.p3):
            Ownership.objects.create(province=p, country=self.old, date_from=dt.date(1900, 1, 1), de_jure=True, de_facto=True)
        # событие 1940: две провинции переходят New, права разные
        self.o1 = Ownership.objects.create(province=self.p1, country=self.new, date_from=dt.date(1940, 1, 1), de_jure=True, de_facto=True)
        self.o2 = Ownership.objects.create(province=self.p2, country=self.new, date_from=dt.date(1940, 1, 1), de_jure=False, de_facto=True)

    def get(self, path, **query):
        return self.client.get(API + path, query).json()

    def post(self, path, body):
        response = self.client.post(API + path, data=json.dumps(body), content_type="application/json")
        return response.status_code, response.json()

    def test_rows_know_the_previous_owner(self):
        rows = {r["id"]: r for r in self.get("", sort="-date")["rows"]}
        self.assertEqual(rows[self.o1.pk]["previous"]["country_code"], "OLD")
        first = next(r for r in rows.values() if r["province"] == self.p3.pk)
        self.assertIsNone(first["previous"])

    def test_events_are_grouped_by_date_and_receiver_with_mixed_rights(self):
        data = self.get("/events")
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["records"], 5)
        top = data["rows"][0]
        self.assertEqual((top["date"], top["country_code"], top["count"]), ("1940-01-01", "NEW", 2))
        self.assertEqual((top["jure"], top["facto"]), (1, 2))
        self.assertEqual([(f["name"], f["count"]) for f in top["froms"]], [("Old", 2)])
        bottom = data["rows"][1]
        self.assertEqual((bottom["country_code"], bottom["count"], bottom["fresh"]), ("OLD", 3, 3))

    def test_events_sorting_and_role_filter(self):
        self.assertEqual([e["count"] for e in self.get("/events", sort="-count")["rows"]], [3, 2])
        gave = self.get("/events", country=self.old.pk, role="from")
        self.assertEqual(gave["total"], 1)                       # Old отдала провинции в событии 1940
        self.assertEqual(gave["rows"][0]["country_code"], "NEW")

    def test_problems_before_birth_after_end_and_duplicates(self):
        early = Ownership.objects.create(province=self.p3, country=self.new, date_from=dt.date(1920, 1, 1), de_jure=True)
        late = Ownership.objects.create(province=self.p3, country=self.old, date_from=dt.date(1950, 1, 1), de_jure=True)
        dup = Ownership.objects.create(province=self.p3, country=self.new, date_from=dt.date(1950, 1, 1), de_jure=True)
        counts = self.get("/problems")
        self.assertEqual((counts["early"], counts["late"], counts["dup"]), (1, 1, 2))
        rows = {r["id"]: r["problem"] for r in self.get("")["rows"]}
        self.assertEqual(rows[early.pk], "early")
        self.assertEqual(rows[late.pk], "late")
        self.assertEqual(rows[dup.pk], "dup")
        self.assertEqual([r["id"] for r in self.get("", problem="early")["rows"]], [early.pk])

    def test_bulk_shift_changes_dates_and_reports_conflicts(self):
        status, preview = self.post("/bulk", {"events": [{"date": "1940-01-01", "country": self.new.pk}], "action": "update", "shift_days": 10, "dry_run": True})
        self.assertEqual((preview["matched"], preview["changed"], preview["conflicts"]), (2, 2, 0))
        self.o1.refresh_from_db()
        self.assertEqual(self.o1.date_from, dt.date(1940, 1, 1))          # предпросмотр ничего не меняет
        status, done = self.post("/bulk", {"events": [{"date": "1940-01-01", "country": self.new.pk}], "action": "update", "shift_days": 10})
        self.assertEqual(done["changed"], 2)
        self.o1.refresh_from_db()
        self.assertEqual(self.o1.date_from, dt.date(1940, 1, 11))
        status, bad = self.post("/bulk", {"ids": [self.o1.pk], "action": "update", "date": "1920-01-01"})
        self.assertEqual((bad["changed"], bad["conflicts"]), (0, 1))      # до рождения страны
        self.assertIn("P-1", bad["examples"][0])

    def test_bulk_rights_and_delete(self):
        status, out = self.post("/bulk", {"ids": [self.o2.pk], "action": "update", "de_jure": True})
        self.assertEqual(out["changed"], 1)
        self.o2.refresh_from_db()
        self.assertTrue(self.o2.de_jure and self.o2.de_facto)
        status, none = self.post("/bulk", {"ids": [self.o2.pk], "action": "update", "de_jure": False, "de_facto": False})
        self.assertEqual((none["changed"], none["conflicts"]), (0, 1))
        status, out = self.post("/bulk", {"events": [{"date": "1940-01-01", "country": self.new.pk}], "action": "delete"})
        self.assertEqual(out["deleted"], 2)
        self.assertFalse(Ownership.objects.filter(country=self.new).exists())
