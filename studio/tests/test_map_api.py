"""Карта в Студии: страны, подписи, провинции, владения, правка территорий и проверка.

Запуск: python manage.py test studio.tests.test_map_api
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from map.models import Country, Ownership, Province

API = "/studio/api/map"


@override_settings(FORCE_SCRIPT_NAME=None)
class MapApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        cls.a = Country.objects.create(code="AAA", name="Alpha", valid_from="1900-01-01")
        cls.b = Country.objects.create(code="BBB", name="Beta", valid_from="1950-01-01")
        cls.p1 = Province.objects.create(code="P1", source_code="s1", name="One")
        cls.p2 = Province.objects.create(code="P2", source_code="s2", name="Two")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def call(self, method, path, body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"{API}{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def test_only_staff_come_in(self):
        self.client.logout()
        self.assertEqual(self.call("get", "/countries")[0], 401)

    def test_a_country_with_labels(self):
        status, made = self.call("post", "/countries", {"code": "CCC", "name": "Gamma", "color": "#112233", "valid_from": "2000-01-01", "predecessor": self.a.pk})
        self.assertEqual((status, made["predecessor_name"]), (200, "Alpha"))
        status, label = self.call("post", f"/countries/{made['id']}/labels", {"text": "", "lng": 10, "lat": 20, "rank": 1})
        self.assertEqual((status, label["country_name"]), (200, "Gamma"))
        self.assertEqual(self.call("get", f"/countries/{made['id']}")[1]["labels"], 1)
        self.assertEqual(self.call("put", f"/labels/{label['id']}", {"text": "Gamma land", "lng": 11, "lat": 21, "rank": 2})[1]["text"], "Gamma land")
        self.assertEqual(len(self.call("get", "/labels?q=gamma")[1]), 1)
        self.assertEqual(self.call("delete", f"/labels/{label['id']}")[0], 200)

    def test_a_country_is_checked(self):
        bad = {"code": "AAA", "name": "Dup", "valid_from": "2000-01-01"}
        self.assertEqual(self.call("post", "/countries", bad)[0], 400)                         # код занят
        self.assertEqual(self.call("post", "/countries", {**bad, "code": "X", "color": "red"})[0], 400)
        self.assertEqual(self.call("put", f"/countries/{self.a.pk}", {"code": "AAA", "name": "A", "valid_from": "1900-01-01", "predecessor": self.a.pk})[0], 400)
        self.assertEqual(self.call("post", "/countries", {**bad, "code": "Y", "valid_to": "1999-01-01"})[0], 400)

    def test_a_country_with_ownerships_cannot_be_deleted(self):
        self.call("post", "/territory/apply", {"codes": ["s1"], "country": self.a.pk, "date": "1960-01-01"})
        status, answer = self.call("delete", f"/countries/{self.a.pk}")
        self.assertEqual(status, 400)
        self.assertEqual(self.call("delete", f"/countries/{self.b.pk}")[0], 200)

    def test_territory_apply_erase_transfer_and_dates(self):
        status, out = self.call("post", "/territory/apply", {"codes": ["s1", "s2", "zz"], "country": self.a.pk, "date": "1960-01-01"})
        self.assertEqual((status, out["created"], out["missing"]), (200, 2, ["zz"]))
        owners = self.call("get", "/territory/owners?date=1970-01-01")[1]
        self.assertEqual((owners["s1"]["country"], owners["s1"]["color"]), (self.a.pk, "#cccccc"))
        self.assertEqual(self.call("get", "/territory/owners?date=1950-01-01")[1], {})
        status, moved = self.call("post", "/territory/transfer", {"source": self.a.pk, "target": self.b.pk, "date": "1970-01-01"})
        self.assertEqual((status, moved["moved"]), (200, 2))
        self.assertEqual(self.call("get", "/territory/dates")[1], ["1960-01-01", "1970-01-01"])
        self.assertEqual(self.call("get", f"/territory/country/{self.b.pk}?date=1970-01-01")[1], ["s1", "s2"])
        self.assertEqual(self.call("post", "/territory/erase", {"codes": ["s1"], "date": "1970-01-01"})[1], {"deleted": 1, "none": 0})
        self.assertEqual(self.call("get", "/territory/owners?date=1980-01-01")[1]["s1"]["country"], self.a.pk)

    def test_territory_refusals_come_as_400_and_404(self):
        self.assertEqual(self.call("post", "/territory/apply", {"codes": [], "country": self.a.pk, "date": "1960-01-01"})[0], 400)
        self.assertEqual(self.call("post", "/territory/apply", {"codes": ["s1"], "country": self.b.pk, "date": "1900-01-01"})[0], 400)
        self.assertEqual(self.call("post", "/territory/apply", {"codes": ["s1"], "country": 999, "date": "1960-01-01"})[0], 404)

    def test_provinces_filter_by_owner_and_date_and_show_history(self):
        self.call("post", "/territory/apply", {"codes": ["s1"], "country": self.a.pk, "date": "1960-01-01"})
        self.call("post", "/territory/apply", {"codes": ["s1"], "country": self.b.pk, "date": "1980-01-01"})
        page = self.call("get", "/provinces?on=1970-01-01")[1]
        self.assertEqual((page["total"], {r["code"]: r["owner"] and r["owner"]["country_name"] for r in page["rows"]}), (2, {"P1": "Alpha", "P2": None}))
        self.assertEqual(self.call("get", "/provinces?owner=none")[1]["total"], 1)
        self.assertEqual(self.call("get", f"/provinces?owner={self.b.pk}")[1]["rows"][0]["code"], "P1")
        self.assertEqual(self.call("get", "/provinces?q=two&limit=1")[1]["total"], 1)
        detail = self.call("get", "/provinces/by-code/s1?on=1970-01-01")[1]
        self.assertEqual([(h["country_code"], h["current"]) for h in detail["history"]], [("BBB", False), ("AAA", True)])
        self.assertEqual(self.call("get", "/provinces/by-code/none")[0], 404)

    def test_a_province_is_created_edited_and_deleted_with_its_records(self):
        status, made = self.call("post", "/provinces", {"code": "P3", "source_code": "s3", "name": "Three"})
        self.assertEqual(status, 200)
        self.assertEqual(self.call("post", "/provinces", {"code": "P3", "source_code": "s4", "name": "Dup"})[0], 400)
        self.call("post", "/territory/apply", {"codes": ["s3"], "country": self.a.pk, "date": "1960-01-01"})
        self.assertEqual(self.call("delete", f"/provinces/{made['id']}")[0], 200)
        self.assertFalse(Ownership.objects.filter(province__source_code="s3").exists())

    def test_ownerships_list_edit_and_bulk_delete(self):
        status, row = self.call("post", "/ownerships", {"province": self.p1.pk, "country": self.a.pk, "date_from": "1960-01-01"})
        self.assertEqual((status, row["country_code"]), (200, "AAA"))
        self.assertEqual(self.call("post", "/ownerships", {"province": self.p1.pk, "country": self.a.pk, "date_from": "1960-01-01"})[0], 400)   # такая есть
        self.assertEqual(self.call("post", "/ownerships", {"province": self.p1.pk, "country": self.b.pk, "date_from": "1900-01-01"})[0], 400)   # вне жизни
        self.assertEqual(self.call("post", "/ownerships", {"province": self.p1.pk, "country": self.a.pk, "date_from": "1961-01-01", "de_jure": False, "de_facto": False})[0], 400)
        self.call("post", "/ownerships", {"province": self.p2.pk, "country": self.a.pk, "date_from": "1970-01-01", "de_jure": False, "de_facto": True})
        self.assertEqual(self.call("get", "/ownerships?flag=facto")[1]["total"], 1)
        self.assertEqual(self.call("get", "/ownerships?after=1965-01-01")[1]["total"], 1)
        self.assertEqual(self.call("get", f"/ownerships?country={self.b.pk}")[1]["total"], 0)
        edited = self.call("put", f"/ownerships/{row['id']}", {"province": self.p1.pk, "country": self.a.pk, "date_from": "1962-01-01"})[1]
        self.assertEqual(edited["date_from"], "1962-01-01")
        self.assertEqual(self.call("post", "/ownerships/delete", {"ids": [row["id"]]})[1], {"deleted": 1})

    def test_checks_report_problems(self):
        codes = {c["code"] for c in self.call("get", "/checks")[1]}
        self.assertIn("no-owner", codes)
