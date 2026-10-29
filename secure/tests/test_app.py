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


class FormatConditionTests(SimpleTestCase):
    """format_condition: обратное к parse_expr, скобки только где нужны."""

    def test_roundtrip_through_the_expression_parser(self):
        from secure.access import format_condition
        from documents.markup import parse_expr

        for text in [
            "key_a",
            "key_a and key_b",
            "key_a or key_b",
            "not key_a",
            "key_a and (key_b or key_c)",
            "(key_a and key_b) or key_c",
            "not (key_a or key_b)",
            "key_a and not key_b",
            "key_a or key_b and key_c",
        ]:
            canonical = format_condition(parse_expr(text))
            self.assertEqual(parse_expr(canonical), parse_expr(text), text)

    def test_readable_output(self):
        from secure.access import format_condition

        self.assertEqual(format_condition({}), "")
        self.assertEqual(format_condition(None), "")
        self.assertEqual(format_condition("key_a"), "key_a")
        self.assertEqual(format_condition({"all": ["a", {"any": ["b", "c"]}]}), "a and (b or c)")
        self.assertEqual(format_condition({"any": [{"all": ["a", "b"]}, "c"]}), "a and b or c")
        self.assertEqual(format_condition({"not": {"any": ["a", "b"]}}), "not (a or b)")
        self.assertEqual(format_condition({"all": ["a", {"not": "b"}]}), "a and not b")
