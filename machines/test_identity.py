"""Данные машины в консоли: имя, hid, серийный номер, адрес.

Запуск: python manage.py test machines.test_identity
"""
from django.test import TestCase

from machines.identity import UNKNOWN_HID, address_for, identity_of, serial_for
from machines.models import Machine


class IdentityTests(TestCase):
    def test_everything_comes_from_the_machine_in_the_database(self):
        machine = Machine.objects.create(name="Main", hostname="aether-main")
        ident = identity_of()
        self.assertEqual((ident.hostname, ident.hid), ("aether-main", machine.hid))
        self.assertEqual(ident.serial, serial_for(machine.hid))
        self.assertEqual(ident.address, address_for(machine.hid))

    def test_a_missing_machine_gets_a_placeholder_not_an_error(self):
        self.assertEqual(identity_of().hid, UNKNOWN_HID)

    def test_serial_and_address_are_stable_for_one_hid_and_differ_between_hids(self):
        self.assertEqual(serial_for("7e:4b:c4:d4:d9:a3"), serial_for("7e:4b:c4:d4:d9:a3"))
        self.assertNotEqual(serial_for("7e:4b:c4:d4:d9:a3"), serial_for("7e:4b:c4:d4:d9:a4"))
        self.assertEqual(address_for("7e:4b:c4:d4:d9:a3"), address_for("7e:4b:c4:d4:d9:a3"))

    def test_serial_and_address_look_right(self):
        self.assertRegex(serial_for("7e:4b:c4:d4:d9:a3"), r"^AE-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]$")
        self.assertRegex(address_for("7e:4b:c4:d4:d9:a3"), r"^10\.40\.\d{1,3}\.\d{1,3}$")

    def test_a_broken_hid_still_gives_an_address(self):
        self.assertEqual(address_for("not-a-mac"), "10.40.0.2")
