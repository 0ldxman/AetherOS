"""air в терминале: приёмник терминала, передача, журнал с момента прихода, скан, позывной.

Запуск: python manage.py test terminal.tests.test_air
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from air import radio
from air.models import Station
from filesystem.testing import make_app
from machines.models import Machine, MachineProfile
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class AirCommandTests(TerminalClient, TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(self.main, label="console", icon="terminal", path="/apps/terminal/")
        self.user = get_user_model().objects.create_user("ivan")
        MachineProfile.objects.create(machine=self.main, user=self.user, name="Ivan", login="ivan", freq=1)
        self.client.force_login(self.user)

    def out(self, text):
        return self.run_command(text)["output"]

    def test_status_tune_transmit_and_log(self):
        self.assertIn("rx 14.230 MHz since", self.out("air"))
        self.assertIn("callsign IVAN", self.out("air"))
        self.assertEqual(self.out("air tune 7.1152"), "rx 7.115 MHz")
        self.assertEqual(self.out("air tx anyone around?"), "tx 7.115 MHz ok")
        self.assertRegex(self.out("air log"), r"^\d\d:\d\d:\d\d  IVAN  anyone around\?$")
        self.out("air tune 7.115")                                                   # заново: журнал с чистого листа
        self.assertIn("no traffic on 7.115", self.out("air log"))
        radio.station_transmit(Station.objects.create(name="CORE"), "7.115", "carrier lost")
        self.assertIn("CORE  carrier lost", self.out("air log 5"))

    def test_errors_and_scan(self):
        self.assertIn("frequency out of band", self.out("air tune 99"))
        self.assertIn("usage", self.out("air bogus"))
        self.out("air tune 14.315")
        self.out("air tx secret")
        scanned = self.out("air scan 14.2 14.5")
        self.assertIn("14.315", scanned)
        self.assertNotIn("secret", scanned)
        self.assertIn("scanner busy", self.out("air scan 14.2 14.5"))

    def test_callsign_and_help(self):
        self.assertEqual(self.out("air call zephyr-7"), "callsign ZEPHYR-7")
        self.assertIn("once a week", self.out("air call north"))
        self.assertIn("air tune <MHz>", self.out("help air"))
