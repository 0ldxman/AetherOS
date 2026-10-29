"""Данные машины в консоли: имя, hid, серийный номер, адрес.

Запуск: python manage.py test machines.tests.test_identity
"""
from django.test import TestCase

from machines.world.identity import (
    FINGERPRINT, UNKNOWN_HID, address_for, address_of, client_fingerprint, fingerprint_for, freq_for, generate_address, generate_host_key,
    generate_serial, identity_of, randomart_for, randomart_of, serial_for,
)
from machines.world.dates import CLEARANCE, CORE_LAST_CONTACT, GAME_DATE, clearance_code, days_since
from machines.models import Machine


class IdentityTests(TestCase):
    def test_everything_comes_from_the_machine_in_the_database(self):
        machine = Machine.objects.create(name="Main", hostname="aether-main")
        ident = identity_of()
        self.assertEqual((ident.hostname, ident.hid), ("aether-main", machine.hid))
        self.assertEqual(ident.serial, serial_for(machine.hid))
        self.assertEqual(ident.address, freq_for(machine.hid))                 # ОС по умолчанию радио: адрес это частота
        self.assertEqual(address_of(machine.hid, "WIN"), address_for(machine.hid))

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


class RadioIdentityTests(TestCase):
    def test_the_frequency_is_in_hf_and_fits_the_profile_field(self):
        for hid in ("7e:4b:c4:d4:d9:a3", "00:00:00:00:00:01", "ff:ff:ff:ff:ff:ff"):
            freq = freq_for(hid)
            self.assertRegex(freq, r"^\d{1,2}\.\d{3}$")
            self.assertTrue(3.0 <= float(freq) < 30.0, freq)

    def test_the_frequency_follows_the_hid(self):
        self.assertEqual(freq_for("7e:4b:c4:d4:d9:a3"), freq_for("7e:4b:c4:d4:d9:a3"))
        self.assertNotEqual(freq_for("7e:4b:c4:d4:d9:a3"), freq_for("7e:4b:c4:d4:d9:a4"))


class OwnIdentityTests(TestCase):
    def test_own_values_of_the_machine_win_over_the_ones_from_hid(self):
        key = generate_host_key()
        Machine.objects.create(name="Main", hostname="aether-main", address="12.345", serial="AE-0000-0000-0", host_key=key)
        ident = identity_of()
        self.assertEqual((ident.address, ident.serial, ident.host_key), ("12.345", "AE-0000-0000-0", key))
        self.assertEqual(ident.randomart, randomart_of(key))

    def test_machines_may_share_a_hid(self):
        Machine.objects.create(name="Main", hostname="aether-main", hid="aa:bb:cc:dd:ee:ff")
        Machine.objects.create(name="Null", hostname="aether-null", hid="aa:bb:cc:dd:ee:ff")
        self.assertEqual(identity_of("aether-main").host_key, identity_of("aether-null").host_key)

    def test_generated_values_look_right(self):
        self.assertRegex(generate_serial(), r"^AE-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]$")
        self.assertRegex(generate_address("WIN"), r"^10\.40\.\d{1,3}\.\d{1,3}$")
        self.assertTrue(3.0 <= float(generate_address("AETHER")) < 30.0)
        self.assertRegex(generate_host_key(), FINGERPRINT.pattern)
        self.assertNotEqual(generate_host_key(), generate_host_key())

    def test_a_typed_fingerprint_draws_the_same_picture_as_the_one_from_hid(self):
        self.assertEqual(randomart_of(fingerprint_for("7e:4b:c4:d4:d9:a3")), randomart_for("7e:4b:c4:d4:d9:a3"))


class WorldTests(TestCase):
    def test_the_player_comes_after_the_hunt(self):
        self.assertGreaterEqual(GAME_DATE.year, 2030)
        self.assertEqual((CORE_LAST_CONTACT.year, CORE_LAST_CONTACT.month), (2027, 10))   # конец октября 2027
        self.assertLess(CORE_LAST_CONTACT, GAME_DATE)

    def test_days_since_is_a_readable_number(self):
        self.assertRegex(days_since(CORE_LAST_CONTACT), r"^\d{1,3}(,\d{3})*$")


class ClearanceLadderTests(TestCase):
    def test_three_letter_greek_codes_for_six_steps(self):
        self.assertEqual(sorted(CLEARANCE), [0, 1, 2, 3, 4, 5])
        for code, name in CLEARANCE.values():
            self.assertRegex(code, r"^[A-Z]{3}$")
            self.assertTrue(name.islower())
        self.assertEqual([clearance_code(n) for n in range(6)], ["MRT", "AKR", "MYS", "EPO", "HIE", "ARC"])

    def test_the_witness_is_the_first_step(self):
        self.assertEqual(clearance_code(0), "MRT")

    def test_an_unknown_level_does_not_break_the_screen(self):
        self.assertEqual(clearance_code(99), "???")

    def test_the_players_own_key_follows_who_they_are(self):
        self.assertEqual(client_fingerprint("user:1"), client_fingerprint("user:1"))
        self.assertNotEqual(client_fingerprint("user:1"), client_fingerprint("user:2"))
        self.assertNotEqual(client_fingerprint("user:1"), fingerprint_for("user:1"))   # не совпадает с ключом узла
