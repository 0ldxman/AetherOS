"""Карточка провинции для приложения карты: что видит игрок, флаги автора и материал (объект)."""
import datetime as dt
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from filesystem.models import Item
from map.info import card
from map.models import Country, Ownership, Province
from map.tests.test_app import SiteTestCase


def build():
    old = Country.objects.create(code="OLD", name="Old", color="#111111", valid_from=dt.date(1900, 1, 1), valid_to=dt.date(1930, 1, 1))
    new = Country.objects.create(code="NEW", name="New", color="#222222", valid_from=dt.date(1930, 1, 1), predecessor=old)
    province = Province.objects.create(code="OLD-1", source_code="XX-1", name="Prov")
    Ownership.objects.create(province=province, country=old, date_from=dt.date(1900, 1, 1), de_jure=True, de_facto=True)
    Ownership.objects.create(province=province, country=new, date_from=dt.date(1930, 1, 1), de_jure=True, de_facto=False)
    return old, new, province


class CardTests(TestCase):
    def test_owner_history_and_country_on_a_date(self):
        old, new, province = build()
        data = card(None, "XX-1", dt.date(1920, 5, 1))
        self.assertEqual(data["owner"]["code"], "OLD")
        self.assertEqual(data["owner"]["rights"], "де-юре и де-факто")
        self.assertEqual([row["code"] for row in data["history"]], ["NEW", "OLD"])
        self.assertEqual([row["current"] for row in data["history"]], [False, True])
        self.assertTrue(data["history"][0]["future"])
        self.assertEqual(data["country"]["code"], "OLD")
        self.assertEqual(data["country"]["successors"], ["New"])
        self.assertEqual(card(None, "XX-1", dt.date(1950, 1, 1))["country"]["predecessor"], "Old")
        self.assertEqual(card(None, "XX-1", dt.date(1950, 1, 1))["owner"]["rights"], "де-юре")

    def test_without_a_date_the_latest_owner_is_shown(self):
        build()
        self.assertEqual(card(None, "XX-1")["owner"]["code"], "NEW")

    def test_the_author_can_hide_a_province_or_only_its_country(self):
        old, new, province = build()
        old.show_info = False
        old.save()
        data = card(None, "XX-1", dt.date(1920, 1, 1))
        self.assertIsNone(data["country"])
        self.assertEqual(data["owner"]["code"], "OLD")          # владелец виден по цвету карты и так
        province.show_info = False
        province.save()
        self.assertIsNone(card(None, "XX-1", dt.date(1920, 1, 1)))

    def test_unknown_province_has_no_card(self):
        self.assertIsNone(card(None, "nope"))

    def test_material_is_shown_only_when_the_player_can_see_it(self):
        old, new, province = build()
        item = Item.objects.create(slug="old-article", name="Old article", format="doc")
        old.material = item
        old.save()
        request = SimpleNamespace()
        page = SimpleNamespace()
        with mock.patch("wiki.views.library", return_value=SimpleNamespace(by_slug={"old-article": page})), \
                mock.patch("wiki.access.document_state", return_value=SimpleNamespace(visible=True)), \
                mock.patch("secure.requestkeys.request_keys", return_value=set()):
            data = card(request, "XX-1", dt.date(1920, 1, 1))
        self.assertEqual(data["material"]["title"], "Old article")
        self.assertTrue(data["material"]["url"].endswith("/go/old-article/"))
        with mock.patch("wiki.views.library", return_value=SimpleNamespace(by_slug={})):
            self.assertIsNone(card(request, "XX-1", dt.date(1920, 1, 1))["material"])

    def test_the_province_material_wins_over_the_country_one_and_external_link_is_the_fallback(self):
        old, new, province = build()
        old.wiki_url = "https://example.com/old"
        old.save()
        data = card(SimpleNamespace(), "XX-1", dt.date(1920, 1, 1))
        self.assertIsNone(data["material"])
        self.assertEqual(data["link"], "https://example.com/old")
        province.wiki_url = "/wiki/own"
        province.save()
        self.assertEqual(card(SimpleNamespace(), "XX-1", dt.date(1920, 1, 1))["link"], "/wiki/own")


class InfoViewTests(SiteTestCase):
    def test_fragment_and_window_and_hidden_province(self):
        old, new, province = build()
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True))
        url = "/apps/map/info/"
        fragment = self.client.get(url, {"code": "XX-1", "date": "1920-05-01", "fragment": "1"})
        self.assertEqual(fragment.status_code, 200)
        self.assertContains(fragment, "Prov")
        self.assertContains(fragment, "OLD")
        self.assertNotContains(fragment, "<html")
        window = self.client.get(url, {"code": "XX-1"})
        self.assertContains(window, "<html")
        province.show_info = False
        province.save()
        self.assertEqual(self.client.get(url, {"code": "XX-1", "fragment": "1"}).status_code, 204)
        self.assertEqual(self.client.get(url, {"code": "XX-1"}).status_code, 404)
