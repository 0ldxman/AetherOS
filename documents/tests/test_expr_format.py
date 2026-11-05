"""Условие доступа: дерево собирается обратно в текст, смысл не меняется.

Запуск: python manage.py test documents.tests.test_expr_format
"""
from django.test import SimpleTestCase

from documents.markup.expr import SpoilerSyntaxError, format_expr, parse_expr

SAMPLES = [
    "cardkey",
    "a and b",
    "a or b",
    "a and (b or not c)",
    "(a or b) and (c or d)",
    "not (a or b)",
    "not not a",
    "a and b and c",
    "a or b and c",
    "(a and b) or (c and d)",
    "not a and not b",
    "a and (b and c)",
    "(a or b) or c",
]


class FormatExprTests(SimpleTestCase):
    def test_every_sample_keeps_its_meaning(self):
        for text in SAMPLES:
            tree = parse_expr(text)
            self.assertEqual(parse_expr(format_expr(tree)), tree, text)

    def test_the_text_is_stable_after_one_pass(self):
        for text in SAMPLES:
            once = format_expr(parse_expr(text))
            self.assertEqual(format_expr(parse_expr(once)), once, text)

    def test_parentheses_only_where_they_matter(self):
        self.assertEqual(format_expr(parse_expr("a or b and c")), "a or b and c")
        self.assertEqual(format_expr(parse_expr("(a or b) and c")), "(a or b) and c")
        self.assertEqual(format_expr(parse_expr("not (a or b)")), "not (a or b)")
        self.assertEqual(format_expr(parse_expr("not a")), "not a")

    def test_trees_built_by_hand_and_empty_pieces(self):
        self.assertEqual(format_expr({"all": ["a", {"any": ["b", {"not": "c"}]}]}), "a and (b or not c)")
        self.assertEqual(format_expr({"all": ["a", "", {"any": []}]}), "a")
        self.assertEqual(format_expr({"all": []}), "")
        self.assertEqual(format_expr({"not": {"all": []}}), "")
        self.assertEqual(format_expr({"all": [{"all": ["a", "b"]}, "c"]}), "(a and b) and c")
        self.assertEqual(format_expr({"any": [{"all": ["a"]}, "b"]}), "a or b")     # группа из одного ключа без скобок

    def test_a_broken_tree_is_refused(self):
        for tree in [{"all": "a"}, {"xor": ["a"]}, {"all": ["a"], "any": ["b"]}, 5]:
            with self.assertRaises(SpoilerSyntaxError):
                format_expr(tree)
