from django.test import SimpleTestCase

from scenes.markup import check, render


def texts(scene):
    return [(s.get("value"), s.get("style")) for s in scene.to_dict() if s["op"] == "text"]


class MarkupTests(SimpleTestCase):
    def test_colours_and_parameters(self):
        scene = render("Hi <success>{login}</success> on {host}", {"login": "ivan", "host": "core"})
        self.assertEqual(texts(scene), [("Hi ", None), ("ivan", "success"), (" on core", None)])

    def test_nested_tags_take_the_inner_style_and_blank_lines_stay(self):
        scene = render("<dim>a <error>b</error> c</dim>\n\nz", {})
        self.assertEqual(texts(scene), [("a ", "dim"), ("b", "error"), (" c", "dim"), ("z", None)])
        self.assertEqual([s["op"] for s in scene.to_dict()].count("newline"), 3)

    def test_escapes(self):
        self.assertEqual(texts(render("{{x}} &lt;b&gt; &amp;", {}))[0][0], "{x} <b> &")

    def test_errors_carry_the_line_number(self):
        found = check("ok\n<b>x</b>\n{nope}\n<dim>open\n</dim>\n{", ["host"])
        self.assertEqual([number for number, _ in found], [2, 2, 3, 4, 5, 6])

    def test_a_missing_value_is_empty(self):
        self.assertEqual(texts(render("a{mail}b", {"mail": None}))[0][0], "ab")

    def test_rand_picks_a_number_from_the_range_and_the_old_name_is_an_error(self):
        self.assertEqual(texts(render("<rand>7-7</rand>%", {}))[0][0], "7%")
        self.assertTrue(0 <= int(texts(render("<rand>0-9</rand>", {}))[0][0]) <= 9)
        self.assertEqual([number for number, _ in check("<random>1-2</random>", [])], [1, 1])
        self.assertTrue(check("<rand>x</rand>", []))
