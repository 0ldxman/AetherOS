from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from secure.access import satisfied, validate_requirements


class SatisfiedTests(SimpleTestCase):
    def test_empty_requirement_is_open(self):
        for req in (None, "", {}, []):
            self.assertTrue(satisfied(req, frozenset()))

    def test_single_key(self):
        self.assertTrue(satisfied("a", {"a"}))
        self.assertFalse(satisfied("a", {"b"}))
        self.assertFalse(satisfied("a", frozenset()))

    def test_all_any_not(self):
        self.assertTrue(satisfied({"all": ["a", "b"]}, {"a", "b"}))
        self.assertFalse(satisfied({"all": ["a", "b"]}, {"a"}))
        self.assertTrue(satisfied({"any": ["a", "b"]}, {"b"}))
        self.assertFalse(satisfied({"any": ["a", "b"]}, frozenset()))
        self.assertTrue(satisfied({"not": "a"}, frozenset()))
        self.assertFalse(satisfied({"not": "a"}, {"a"}))

    def test_nested(self):
        req = {"all": ["a", {"any": ["b", {"not": "c"}]}]}
        self.assertTrue(satisfied(req, {"a"}))
        self.assertFalse(satisfied(req, {"a", "c"}))
        self.assertTrue(satisfied(req, {"a", "b", "c"}))

    def test_unknown_operator_closes_access(self):
        self.assertFalse(satisfied({"xor": ["a", "b"]}, {"a", "b"}))


class ValidateRequirementsTests(SimpleTestCase):
    def test_valid(self):
        for req in (None, "", {}, "a", {"all": ["a", "b"]}, {"not": "a"},
                    {"any": ["a", {"not": "b"}]}):
            validate_requirements(req)

    def test_invalid(self):
        for req in (5, ["a"], {"all": []}, {"all": "a"}, {"not": ""},
                    {"xor": ["a"]}, {"all": ["a"], "any": ["b"]},
                    {"all": [5]}):
            with self.assertRaises(ValidationError, msg=repr(req)):
                validate_requirements(req)
