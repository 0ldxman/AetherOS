"""Эфир в Студии: лента с настоящими игроками, модерация, позывные, станции, полосы, жалобы, права раздела."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from air import radio
from air.models import Station, Transmission
from team.models import Role
from team.testing import full_role

API = "/studio/api"


class AirApiTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.client.force_login(self.author)
        self.ivan = get_user_model().objects.create_user("ivan")

    def call(self, method, path, body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"{API}{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def test_feed_shows_who_is_behind_a_callsign_and_moderation_works(self):
        sent = radio.transmit(self.ivan, "7.115", "hello")
        radio.report(sent, get_user_model().objects.create_user("olga"), "spam")
        status, rows = self.call("get", "/air/feed")
        self.assertEqual(status, 200)
        self.assertEqual((rows[0]["callsign"], rows[0]["player"]["username"], rows[0]["reports"]), ("IVAN", "ivan", 1))
        self.assertEqual(self.call("get", "/air/feed?freq=7.120")[1], [])
        self.assertEqual(len(self.call("get", "/air/feed?q=hel")[1]), 1)
        self.assertEqual(len(self.call("get", f"/air/feed?after={sent.pk}")[1]), 0)
        self.assertEqual(len(self.call("get", "/air/reports")[1]), 1)
        hidden = self.call("post", f"/air/transmissions/{sent.pk}/hide", {"reason": "spam"})[1]
        self.assertTrue(hidden["hidden"])
        self.assertEqual(self.call("get", "/air/reports")[1], [])                    # скрытие закрыло жалобу
        self.assertFalse(self.call("post", f"/air/transmissions/{sent.pk}/unhide")[1]["hidden"])

    def test_callsigns_mute_and_take_the_transmitter(self):
        radio.callsign_of(self.ivan)
        status, sign = self.call("put", f"/air/callsigns/{self.ivan.pk}", {"name": "zephyr", "rx_only": True})
        self.assertEqual((status, sign["name"], sign["rx_only"], sign["history"][0]["by"]), (200, "ZEPHYR", True, "boss"))
        with self.assertRaises(radio.AirError):
            radio.transmit(self.ivan, "7.115", "x")
        sign = self.call("put", f"/air/callsigns/{self.ivan.pk}", {"rx_only": False, "mute_minutes": 30})[1]
        self.assertIsNotNone(sign["muted_until"])
        self.assertEqual(self.call("put", f"/air/callsigns/{self.ivan.pk}", {"mute_minutes": 0})[1]["muted_until"], None)
        self.assertEqual([s["name"] for s in self.call("get", "/air/callsigns?q=zep")[1]], ["ZEPHYR"])

    def test_stations_bands_and_station_transmissions(self):
        status, core = self.call("post", "/air/stations", {"name": "core", "label": "ядро", "kind": "station"})
        self.assertEqual((status, core["name"]), (200, "CORE"))
        self.assertEqual(self.call("post", "/air/stations", {"name": "CORE"})[0], 400)
        band = self.call("post", "/air/bands", {"low": "10.1", "high": "10", "kind": "reserved", "label": "beacons"})[1]
        self.assertEqual((band["low"], band["high"]), ("10.000", "10.100"))
        sent = self.call("post", "/air/transmit", {"station": core["id"], "freq": "10.05", "text": "beacon"})[1]
        self.assertEqual((sent["callsign"], sent["station"]), ("CORE", True))
        with self.assertRaises(radio.AirError):
            radio.transmit(self.ivan, "10.05", "x")
        self.assertEqual(self.call("delete", f"/air/bands/{band['id']}")[0], 204)
        self.assertEqual(self.call("delete", f"/air/stations/{core['id']}")[0], 204)

    def test_the_section_needs_rights(self):
        reader = get_user_model().objects.create_user("reader", is_staff=True, role=Role.objects.create(name="r", rights={"air": "read"}))
        self.client.force_login(reader)
        self.assertEqual(self.call("get", "/air/feed")[0], 200)
        sent = radio.transmit(self.ivan, "7.115", "x")
        self.assertEqual(self.call("post", f"/air/transmissions/{sent.pk}/hide", {"reason": ""})[0], 403)
