"""Эфир: частоты, позывные, передача и приём «с момента прихода», скан, модерация, хранение 24 часа, песочница."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from air import radio
from air.models import Band, Callsign, CallsignChange, Station, Transmission


class AirTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.olga = get_user_model().objects.create_user("olga")
        self.t0 = timezone.now()

    def tx(self, user, freq, text, seconds=0):
        return radio.transmit(user, freq, text, now=self.t0 + timedelta(seconds=seconds))

    def test_frequencies_snap_to_the_grid_and_stay_in_band(self):
        self.assertEqual(radio.parse_freq("14.23"), Decimal("14.230"))
        self.assertEqual(radio.parse_freq("7,1152"), Decimal("7.115"))
        self.assertEqual(radio.parse_freq("7.1176"), Decimal("7.120"))
        for bad in ("2.990", "30.010", "abc", "nan"):
            with self.assertRaises(radio.AirError):
                radio.parse_freq(bad)

    def test_callsigns_come_from_the_name_are_unique_and_reserved(self):
        Station.objects.create(name="CORE")
        core = get_user_model().objects.create_user("core")
        self.assertEqual(radio.callsign_of(self.ivan).name, "IVAN")
        self.assertEqual(radio.callsign_of(core).name, "CORE-2")                    # имя станции занято
        with self.assertRaises(radio.AirError):
            radio.rename(self.olga, "CORE")
        with self.assertRaises(radio.AirError):
            radio.rename(self.olga, "IVAN")
        with self.assertRaises(radio.AirError):
            radio.rename(self.olga, "9lives")
        radio.rename(self.olga, "zephyr-7")
        self.assertEqual(Callsign.objects.get(user=self.olga).name, "ZEPHYR-7")
        with self.assertRaises(radio.AirError):
            radio.rename(self.olga, "NORTH")                                         # раз в неделю
        author = get_user_model().objects.create_user("boss", is_staff=True)
        radio.rename(self.olga, "NORTH", by=author)                                  # автору можно
        self.assertEqual(list(CallsignChange.objects.filter(user=self.olga).values_list("new", flat=True)), ["NORTH", "ZEPHYR-7"])

    def test_a_listener_hears_only_what_came_after_tuning_in(self):
        self.tx(self.ivan, "7.115", "before")
        tuned = self.t0 + timedelta(seconds=1)
        self.tx(self.ivan, "7.115", "after", seconds=3)
        self.tx(self.ivan, "7.120", "elsewhere", seconds=6)
        heard = radio.listen(self.olga, "7.115", since=tuned, now=self.t0 + timedelta(seconds=10))
        self.assertEqual([row["text"] for row in heard], ["after"])
        again = radio.listen(self.olga, "7.115", since=tuned, after=heard[-1]["id"], now=self.t0 + timedelta(seconds=10))
        self.assertEqual(again, [])

    def test_transmit_rules(self):
        Band.objects.create(low=Decimal("10.000"), high=Decimal("10.100"), kind=Band.Kind.RESERVED, label="beacons")
        with self.assertRaises(radio.AirError):
            self.tx(self.ivan, "10.050", "hi")                                       # полоса станций
        sent = self.tx(self.ivan, "7.115", "see https://evil.example/x and www.spam.com here")
        self.assertEqual(sent.text, "see and here")                                  # ссылки вырезаны
        with self.assertRaises(radio.AirError):
            self.tx(self.ivan, "7.115", "again", seconds=1)                          # не чаще раза в 2 секунды
        with self.assertRaises(radio.AirError):
            self.tx(self.ivan, "7.115", "x" * 281, seconds=5)
        with self.assertRaises(radio.AirError):
            self.tx(self.ivan, "7.115", "http://only.link", seconds=5)
        radio.set_rx_only(self.ivan, True)
        with self.assertRaises(radio.AirError):
            self.tx(self.ivan, "7.115", "x", seconds=10)
        radio.set_rx_only(self.ivan, False)
        radio.silence(self.ivan, 30)
        with self.assertRaises(radio.AirError):
            radio.transmit(self.ivan, "7.115", "x")

    def test_rate_per_minute(self):
        for n in range(radio.PER_MINUTE):
            self.tx(self.ivan, "7.115", f"m{n}", seconds=n * 2.5 if n < 20 else 0)
        with self.assertRaises(radio.AirError):
            self.tx(self.ivan, "7.115", "one more", seconds=radio.PER_MINUTE * 2.5 - 10)

    def test_conditional_bands_and_guests(self):
        Band.objects.create(low=Decimal("21.000"), high=Decimal("21.050"), kind=Band.Kind.CONDITIONAL, condition="door_key")
        self.assertFalse(radio.can_listen(Decimal("21.010"), set()))
        self.assertTrue(radio.can_listen(Decimal("21.010"), {"door_key"}))
        self.assertTrue(radio.can_listen(radio.CALLING, set(), guest=True))
        self.assertFalse(radio.can_listen(Decimal("7.115"), set(), guest=True))

    def test_scan_shows_activity_without_text(self):
        self.tx(self.ivan, "14.315", "secret")
        self.tx(self.olga, "14.315", "reply", seconds=1)
        self.tx(self.ivan, "14.700", "far", seconds=3)
        found = radio.scan(self.olga, "14.200", "14.500", now=self.t0 + timedelta(seconds=10))
        self.assertEqual([(row["freq"], row["count"]) for row in found], [(Decimal("14.315"), 2)])
        self.assertNotIn("text", found[0])
        self.assertEqual(radio.scan(self.olga, "14.200", "14.500", now=self.t0 + timedelta(minutes=20)), [])
        with self.assertRaises(radio.AirError):
            radio.scan(self.olga, "14.000", "15.000")

    def test_hidden_transmissions_read_as_noise(self):
        sent = self.tx(self.ivan, "7.115", "bad words")
        radio.report(sent, self.olga, "rude")
        author = get_user_model().objects.create_user("boss", is_staff=True)
        radio.hide(sent, author, "rude")
        heard = radio.listen(self.olga, "7.115", since=self.t0 - timedelta(seconds=1), now=self.t0 + timedelta(seconds=1))
        self.assertEqual((heard[0]["text"], heard[0]["hidden"]), (radio.NOISE, True))
        self.assertIsNotNone(sent.reports.get().resolved_at)

    def test_only_24_hours_are_kept(self):
        old = self.tx(self.ivan, "7.115", "old")
        Transmission.objects.filter(pk=old.pk).update(created_at=self.t0 - timedelta(hours=25))
        self.tx(self.olga, "7.115", "new", seconds=1)
        self.assertEqual(list(Transmission.objects.values_list("text", flat=True)), ["new"])

    def test_the_sandbox_player_is_heard_only_by_itself(self):
        from users import sandbox

        author = get_user_model().objects.create_user("anna", is_staff=True)
        player = sandbox.sandbox_of(author)
        self.tx(player, "7.115", "testing")
        since = self.t0 - timedelta(seconds=1)
        now = self.t0 + timedelta(seconds=1)
        self.assertEqual(radio.listen(self.olga, "7.115", since=since, now=now), [])
        self.assertEqual([row["text"] for row in radio.listen(player, "7.115", since=since, now=now)], ["testing"])
        self.assertEqual(radio.scan(self.olga, "7.000", "7.200", now=now), [])

    def test_stations_transmit_anywhere(self):
        Band.objects.create(low=Decimal("10.000"), high=Decimal("10.100"), kind=Band.Kind.RESERVED)
        core = Station.objects.create(name="CORE", kind=Station.Kind.STATION)
        sent = radio.station_transmit(core, "10.050", "carrier lost: boreas")
        heard = radio.listen(self.ivan, "10.050", since=self.t0 - timedelta(seconds=5))
        self.assertEqual((heard[0]["callsign"], heard[0]["station"]), ("CORE", True))
        self.assertEqual(sent.station, core)
