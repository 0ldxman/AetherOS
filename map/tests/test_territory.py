import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase

from map import territory
from map.models import Country, CountryLabel, Ownership, Province

D = dt.date


def make():
    a = Country.objects.create(code="AAA", name="Alpha", valid_from=D(1900, 1, 1))
    b = Country.objects.create(code="BBB", name="Beta", valid_from=D(1950, 1, 1))
    p1 = Province.objects.create(code="P1", source_code="s1", name="One")
    p2 = Province.objects.create(code="P2", source_code="s2", name="Two")
    return a, b, p1, p2


class ApplyTests(TestCase):
    def setUp(self):
        self.a, self.b, self.p1, self.p2 = make()

    def test_apply_creates_updates_and_skips(self):
        out = territory.apply_ownership(["s1", "s2", "nope"], self.a, D(1960, 1, 1))
        self.assertEqual((out["created"], out["updated"], out["unchanged"], out["missing"]), (2, 0, 0, ["nope"]))
        again = territory.apply_ownership(["s1"], self.a, D(1960, 1, 1))
        self.assertEqual((again["created"], again["unchanged"]), (0, 1))
        moved = territory.apply_ownership(["s1"], self.b, D(1960, 1, 1))
        self.assertEqual((moved["updated"], Ownership.objects.filter(province=self.p1).count()), (1, 1))
        inherited = territory.apply_ownership(["s2"], self.a, D(1970, 1, 1))
        self.assertEqual((inherited["created"], inherited["unchanged"]), (0, 1))   # на эту дату владение и так такое

    def test_later_records_are_kept_and_counted(self):
        territory.apply_ownership(["s1"], self.a, D(1980, 1, 1))
        out = territory.apply_ownership(["s1"], self.b, D(1960, 1, 1))
        self.assertEqual(out["later"], 1)
        self.assertEqual(territory.owners_on(D(1990, 1, 1))["s1"]["country"], self.a.pk)
        self.assertEqual(territory.owners_on(D(1970, 1, 1))["s1"]["country"], self.b.pk)

    def test_refusals(self):
        for call in (
            lambda: territory.apply_ownership([], self.a, D(1960, 1, 1)),
            lambda: territory.apply_ownership(["s1"], self.b, D(1900, 1, 1)),       # страны ещё нет
            lambda: territory.apply_ownership(["s1"], self.a, D(1960, 1, 1), False, False),
            lambda: territory.apply_ownership("s1", self.a, D(1960, 1, 1)),
        ):
            with self.assertRaises(territory.TerritoryError):
                call()
        self.assertEqual(Ownership.objects.count(), 0)

    def test_erase_restores_the_previous_owner(self):
        territory.apply_ownership(["s1"], self.a, D(1960, 1, 1))
        territory.apply_ownership(["s1"], self.b, D(1970, 1, 1))
        out = territory.erase_ownership(["s1", "s2"], D(1970, 1, 1))
        self.assertEqual(out, {"deleted": 1, "none": 1})
        self.assertEqual(territory.owners_on(D(1975, 1, 1))["s1"]["country"], self.a.pk)

    def test_transfer_moves_everything_the_country_owns(self):
        territory.apply_ownership(["s1", "s2"], self.a, D(1960, 1, 1))
        out = territory.transfer_country(self.a, self.b, D(1970, 1, 1))
        self.assertEqual(out["moved"], 2)
        self.assertEqual(territory.provinces_of(self.b, D(1970, 1, 1)), ["s1", "s2"])
        self.assertEqual(territory.provinces_of(self.a, D(1965, 1, 1)), ["s1", "s2"])
        with self.assertRaises(territory.TerritoryError):
            territory.transfer_country(self.a, self.b, D(1971, 1, 1))     # у Alpha уже ничего нет
        with self.assertRaises(territory.TerritoryError):
            territory.transfer_country(self.a, self.a, D(1971, 1, 1))


class ChecksTests(TestCase):
    def test_checks_find_what_is_wrong(self):
        a, b, p1, p2 = make()
        territory.apply_ownership(["s1"], a, D(1960, 1, 1))
        Ownership.objects.create(province=p1, country=b, date_from=D(1960, 1, 1), de_facto=True)      # две страны на одну дату
        Ownership.objects.create(province=p1, country=b, date_from=D(1900, 1, 1), de_facto=True)      # раньше жизни страны
        b.valid_to = D(1990, 1, 1)
        b.save()
        found = {c["code"]: c for c in territory.checks()}
        self.assertEqual(found["no-owner"]["count"], 1)
        self.assertEqual(found["same-day"]["count"], 1)
        self.assertEqual(found["outside-life"]["count"], 1)
        self.assertIn("no-label", found)
        CountryLabel.objects.create(country=a, lng=1, lat=1)
        labels = {c["code"]: c for c in territory.checks()}["no-label"]
        self.assertEqual([i["label"] for i in labels["items"]], ["Beta (BBB)"])

    def test_check_items_give_all_findings_with_search_and_targets(self):
        a, b, p1, p2 = make()
        territory.apply_ownership(["s1"], a, D(1960, 1, 1))
        page = territory.check_items("no-owner")
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["rows"][0]["province_id"], p2.pk)
        self.assertEqual(territory.check_items("no-owner", "нет такого")["total"], 0)
        idle = territory.check_items("idle-country")
        self.assertEqual([r["country_id"] for r in idle["rows"]], [b.pk])
        self.assertEqual(territory.check_items("idle-country", limit=1, offset=1)["rows"], [])
        with self.assertRaises(territory.TerritoryError) as caught:
            territory.check_items("nope")
        self.assertEqual(caught.exception.status, 404)


class AdminApplyTests(TestCase):
    def test_the_old_admin_endpoint_keeps_its_answers(self):
        import json

        a, b, p1, p2 = make()
        staff = get_user_model().objects.create_superuser("root", password="pw")
        self.client.force_login(staff)
        url = "/admin/map/ownership/editor/apply/"
        post = lambda body: self.client.post(url, json.dumps(body), content_type="application/json")
        ok = post({"codes": ["s1"], "country": a.pk, "date": "1960-01-01"})
        self.assertEqual((ok.status_code, ok.json()["created"]), (200, 1))
        self.assertEqual(post({"codes": [], "country": a.pk, "date": "1960-01-01"}).status_code, 400)
        self.assertEqual(post({"codes": ["s1"], "country": 999, "date": "1960-01-01"}).status_code, 404)
        self.assertEqual(post({"codes": ["s1"], "country": b.pk, "date": "1900-01-01"}).status_code, 400)
