"""Данные машины в консоли: имя, hid, серийный номер, адрес.

Запуск: python manage.py test machines.test_identity
"""
from django.test import TestCase

from machines.identity import UNKNOWN_HID, address_for, fingerprint_for, identity_of, randomart_for, serial_for
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


class HostKeyTests(TestCase):
    def test_the_fingerprint_looks_like_ssh_and_is_stable(self):
        fp = fingerprint_for("7e:4b:c4:d4:d9:a3")
        self.assertRegex(fp, r"^SHA256:[A-Za-z0-9+/]{43}$")
        self.assertEqual(fp, fingerprint_for("7e:4b:c4:d4:d9:a3"))
        self.assertNotEqual(fp, fingerprint_for("7e:4b:c4:d4:d9:a4"))

    def test_randomart_is_a_framed_17x9_picture_with_start_and_end(self):
        art = randomart_for("7e:4b:c4:d4:d9:a3")
        self.assertEqual(len(art), 11)
        self.assertEqual({len(line) for line in art}, {19})
        self.assertTrue(art[0].startswith("+") and "[ED25519 256]" in art[0])
        self.assertIn("[SHA256]", art[-1])
        picture = "".join(art[1:-1])
        self.assertIn("S", picture)

    def test_the_picture_follows_the_key(self):
        self.assertEqual(randomart_for("7e:4b:c4:d4:d9:a3"), randomart_for("7e:4b:c4:d4:d9:a3"))
        self.assertNotEqual(randomart_for("7e:4b:c4:d4:d9:a3"), randomart_for("00:00:00:00:00:01"))

    def test_identity_carries_both(self):
        machine = Machine.objects.create(name="Main", hostname="aether-main")
        ident = identity_of()
        self.assertEqual(ident.host_key, fingerprint_for(machine.hid))
        self.assertEqual(ident.randomart, randomart_for(machine.hid))
