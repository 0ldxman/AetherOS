"""Шифр эфира: Виженер, ключ на приёмнике, что видит слушатель с ключом и без, станции с ключом."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from air import cipher, events, radio
from air.models import Responder, Station


class CipherTests(TestCase):
    def test_vigenere_keeps_case_digits_and_both_alphabets(self):
        sent = cipher.encrypt("Boreas, ловим в 21:00!", "Ключ")
        self.assertNotEqual(sent, "Boreas, ловим в 21:00!")
        self.assertTrue(sent[0].isupper() and sent.endswith("21:00!"))
        self.assertEqual(cipher.decrypt(sent, "ключ"), "Boreas, ловим в 21:00!")         # регистр ключа не важен
        self.assertEqual(cipher.encrypt("abc", "b"), "bcd")
        self.assertEqual(cipher.normalize("  --  "), "")                                    # без букв и цифр ключа нет
        self.assertEqual(cipher.mark("Orpheus"), cipher.mark("orpheus"))
        self.assertEqual(cipher.mark(""), "")


class KeyedAirTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.olga = get_user_model().objects.create_user("olga")
        self.now = timezone.now()

    def heard(self, user, key=""):
        return [(row["text"], row["foreign"]) for row in radio.listen(user, "7.115", self.now - timedelta(minutes=5), now=self.now + timedelta(seconds=30), air_key=key)]

    def test_who_sees_what(self):
        radio.transmit(self.ivan, "7.115", "meet at dawn", now=self.now, air_key="orpheus")
        radio.transmit(self.ivan, "7.115", "open hello", now=self.now + timedelta(seconds=3))
        same, none, other = self.heard(self.olga, "Orpheus"), self.heard(self.olga), self.heard(self.olga, "eurydice")
        self.assertEqual(same[0], ("meet at dawn", False))                    # тот же ключ: открытый текст
        self.assertTrue(same[1][1] and same[1][0] != "open hello")            # открытое со своим ключом: каша, бледно
        self.assertEqual(none[0], (cipher.encrypt("meet at dawn", "orpheus"), True))    # без ключа: шифровка, бледно
        self.assertEqual(none[1], ("open hello", False))
        self.assertTrue(other[0][1] and other[0][0] != "meet at dawn")

    def test_a_station_listens_and_answers_in_its_key(self):
        station = Station.objects.create(name="BOREAS")
        Responder.objects.create(station=station, freq=Decimal("7.115"), pattern="qrz", reply="QSL {callsign}", delay=0, key="orpheus")
        radio.transmit(self.ivan, "7.115", "qrz", now=self.now)                               # открытым текстом: станция не поймёт
        radio.transmit(self.ivan, "7.115", "qrz", now=self.now + timedelta(seconds=3), air_key="orpheus")
        events.flush(self.now + timedelta(seconds=10))
        answers = [text for text, _ in self.heard(self.olga, "orpheus") if text.startswith("QSL")]
        self.assertEqual(answers, ["QSL IVAN"])
