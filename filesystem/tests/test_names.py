"""Правила имён внутри тома: одни для автора и игрока.

Запуск: python manage.py test filesystem.tests.test_names
"""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from filesystem.names import normalize_mount, validate_name


class NameTests(SimpleTestCase):
    def test_ordinary_names_pass(self):
        for name in ("report.rec", ".secrets", "Отчёт 7.doc", "a b", "x" * 255):
            validate_name(name)

    def test_bad_names_are_refused(self):
        for name in ("", " ", " lead", "tail ", ".", "..", "a/b", "a\\b", "C:", "x" * 256, "a\x00b", "line\nbreak", "tab\there", "del\x7f"):
            with self.assertRaises(ValidationError, msg=repr(name)):
                validate_name(name)

    def test_a_drive_is_allowed_only_at_the_start_of_a_mount_point(self):
        self.assertEqual(normalize_mount("c:\\Users"), "/C:/Users")
        with self.assertRaises(ValidationError):
            normalize_mount("/mnt/C:")
