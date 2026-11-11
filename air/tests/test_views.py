"""Приложение «эфир» у игрока: выход на частоту, приём с момента прихода, передача, скан, позывной, гость."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from air import radio
from air.models import Station, Transmission
from filesystem.testing import make_app
from machines.models import Machine


@override_settings(FORCE_SCRIPT_NAME=None)
class AirAppTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        self.null = Machine.objects.create(name="Null", hostname="aether-null")
        make_app(self.null, label="air", icon="radio", path="/apps/air/")          # гость сидит на aether-null
        make_app(self.main, label="air", icon="radio", path="/apps/air/")
        self.ivan = get_user_model().objects.create_user("ivan")
        self.client.force_login(self.ivan)

    def post(self, name, body):
        response = self.client.post(reverse(f"air:{name}"), data=json.dumps(body), content_type="application/json")
        return response.status_code, response.json()

    def listen(self, after=0):
        return self.client.get(reverse("air:listen"), {"after": after}).json()

    def test_opening_the_app_tunes_in_fresh_on_the_calling_channel(self):
        Station.objects.create(name="CORE")
        radio.station_transmit(Station.objects.get(), "14.230", "old news")
        html = self.client.get(reverse("air:index")).content.decode()
        self.assertIn('"freq": "14.230"', html)
        self.assertIn('"callsign": "IVAN"', html)
        self.assertEqual(self.listen()["rows"], [])                                   # то, что было до прихода, не слышно
        radio.station_transmit(Station.objects.get(), "14.230", "carrier lost")
        self.assertEqual([row["text"] for row in self.listen()["rows"]], ["carrier lost"])

    def test_tune_transmit_and_hear_yourself(self):
        self.client.get(reverse("air:index"))
        status, state = self.post("tune", {"freq": "7.1152"})
        self.assertEqual((status, state["freq"]), (200, "7.115"))
        status, sent = self.post("tx", {"text": "anyone here?"})
        self.assertEqual(status, 200)
        rows = self.listen()["rows"]
        self.assertEqual((rows[0]["callsign"], rows[0]["text"], rows[0]["mine"]), ("IVAN", "anyone here?", True))
        self.assertEqual(self.listen(rows[-1]["id"])["rows"], [])
        self.assertEqual(Transmission.objects.get().machine, self.main)
        self.assertEqual(self.post("tune", {"freq": "40"})[0], 400)
        self.assertEqual(self.post("tx", {"text": "again"})[0], 400)                    # не чаще раза в 2 секунды

    def test_scan_is_rate_limited(self):
        self.client.get(reverse("air:index"))
        self.post("tune", {"freq": "14.315"})
        self.post("tx", {"text": "secret"})
        found = self.client.get(reverse("air:scan"), {"low": "14.200", "high": "14.500"}).json()
        self.assertEqual(found["rows"][0]["freq"], "14.315")
        self.assertNotIn("text", found["rows"][0])
        self.assertEqual(self.client.get(reverse("air:scan"), {"low": "14.200", "high": "14.500"}).status_code, 429)

    def test_callsign_change(self):
        self.client.get(reverse("air:index"))
        self.assertEqual(self.post("callsign", {"name": "zephyr-7"}), (200, {"callsign": "ZEPHYR-7"}))
        self.assertEqual(self.post("callsign", {"name": "north"})[0], 400)               # раз в неделю

    def test_guests_listen_only_to_the_calling_channel(self):
        self.client.logout()
        session = self.client.session
        session["guest"] = True
        session.save()
        html = self.client.get(reverse("air:index")).content.decode()
        self.assertIn('"can_tx": false', html)
        self.assertEqual(self.post("tune", {"freq": "7.115"})[0], 403)
        self.assertEqual(self.post("tx", {"text": "hi"})[0], 403)
