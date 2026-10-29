from datetime import datetime, timezone

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


def lines_of(scene):
    out, row = [], ""
    for step in scene.to_dict():
        if step["op"] == "text":
            row += step["value"]
        elif step["op"] == "newline":
            out.append(row)
            row = ""
    return out


class TableTests(SimpleTestCase):
    TEMPLATE = "<table>\n  NAME: | {host} | CHAN: | {chan}\n  SERIAL: | {serial} | HID: | {hid}\n  CORE: | <error>down</error>\n</table>"

    def render(self, host):
        return lines_of(render(self.TEMPLATE, {"host": host, "chan": "25.568", "serial": "AE-1", "hid": "aa"}))

    def test_columns_stay_aligned_whatever_the_values_are(self):
        for host in ("aether-main", "gw-2", "a-very-long-gateway-name"):
            rows = self.render(host)
            self.assertEqual(rows[0].index("CHAN:"), rows[1].index("HID:"))
            self.assertEqual(rows[0].index(host), rows[1].index("AE-1"))
            self.assertEqual(rows[0].index("CHAN:"), max(len("  NAME:"), len("  SERIAL:")) + 3 + max(len(host), len("AE-1")) + 3)
            self.assertEqual(rows[2], "  CORE:     down")

    def test_the_widest_cell_sets_the_column_and_gap_is_adjustable(self):
        rows = lines_of(render("<table gap=1>\na | b\nlonger | c\n</table>", {}))
        self.assertEqual(rows, ["a      b", "longer c"])

    def test_colours_work_inside_cells_and_do_not_count_as_width(self):
        scene = render("<table gap=1>\n<success>ok</success> | x\nlonger | y\n</table>", {})
        self.assertEqual(lines_of(scene), ["ok     x", "longer y"])
        self.assertEqual([s.get("style") for s in scene.to_dict() if s["op"] == "text"][0], "success")

    def test_the_pipe_can_be_written_and_unclosed_tables_are_errors(self):
        self.assertEqual(lines_of(render("<table>\na &pipe; b | c\n</table>", {})), ["a | b   c"])
        self.assertEqual([n for n, _ in check("<table>\na | b", [])], [1])
        self.assertEqual([n for n, _ in check("a\n</table>", [])], [2])
        self.assertEqual([n for n, _ in check("<table>\n{nope} | b\n</table>", [])], [2])


class SinceTests(SimpleTestCase):
    NOW = datetime(2030, 11, 14, 3, 14, tzinfo=timezone.utc)

    def shown(self, template, params=None):
        scene = render(template, params or {}, now=self.NOW)
        return "".join(step["value"] for step in scene.to_dict() if step["op"] == "text")

    def test_formats(self):
        self.assertEqual(self.shown("<since>2027-10-29</since>"), "1,112")
        self.assertEqual(self.shown("<since>2027-10-29 | days</since>"), "1,112")
        self.assertEqual(self.shown("<since>2030-11-14 | hours</since>"), "3")
        self.assertEqual(self.shown("<since>2030-11-14 03:00 | minutes</since>"), "14")
        self.assertEqual(self.shown("<since>2027-10-29 | years</since>"), "3")
        self.assertEqual(self.shown("<since>2027-10-29 | ymd</since>"), "3 y 0 mo 16 d")
        self.assertEqual(self.shown("<since>2027-10-29 | ago</since>"), "1,112 d")
        self.assertEqual(self.shown("<since>2030-11-14 03:00 | ago</since>"), "14 min")
        self.assertEqual(self.shown("<since>2030-11-20 | ago</since>"), "in 5 d")

    def test_the_date_may_come_from_a_parameter_and_text_around_stays(self):
        self.assertEqual(self.shown("gone for <since>{when}</since> days", {"when": "2030-11-04"}), "gone for 10 days")

    def test_a_table_cell_keeps_the_bar_inside_since(self):
        rows = lines_of(render("<table gap=1>\nCORE: | <since>2027-10-29 | days</since> d\nUP: | x\n</table>", {}, now=self.NOW))
        self.assertEqual(rows, ["CORE: 1,112 d", "UP:   x"])

    def test_errors_name_the_line(self):
        self.assertEqual([n for n, _ in check("ok\n<since>nope</since>\n<since>2027-10-29 | weeks</since>", [])], [2, 3])
