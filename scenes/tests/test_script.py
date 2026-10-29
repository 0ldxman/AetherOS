from datetime import datetime, timezone

from django.test import SimpleTestCase

from scenes.script import check_script, compile_script

NOW = datetime(2030, 11, 14, 3, 14, tzinfo=timezone.utc)


def ops(source, params=None, resolve=None):
    scene, errors = compile_script(source, params or {}, NOW, resolve)
    return scene.to_dict(), errors


def kinds(steps):
    return [step["op"] for step in steps]


class LinesTests(SimpleTestCase):
    def test_plain_lines_dim_lines_blank_lines_and_escapes(self):
        steps, errors = ops("Hello <success>{who}</success>\n~ quiet\n\n\\@ not a step", {"who": "ivan"})
        self.assertEqual(errors, [])
        texts = [(s["value"], s.get("style")) for s in steps if s["op"] == "text"]
        self.assertEqual(texts, [("Hello ", None), ("ivan", "success"), ("quiet", "dim"), ("@ not a step", None)])
        self.assertEqual(kinds(steps).count("newline"), 4)

    def test_a_table_block_is_aligned(self):
        steps, errors = ops("<table gap=1>\na | b\nlonger | c\n</table>")
        self.assertEqual(errors, [])
        self.assertEqual("".join(s["value"] if s["op"] == "text" else "\n" for s in steps).splitlines(), ["a      b", "longer c"])


class InlineTests(SimpleTestCase):
    def test_a_count_lives_inside_a_line(self):
        steps, errors = ops("Memory Testing:  <count to=64000 unit=K ms=600-1100/>  <success>OK</success>  <dim>ecc</dim>")
        self.assertEqual(errors, [])
        self.assertEqual(kinds(steps), ["text", "count", "text", "text", "text", "text", "newline"])
        count = steps[1]
        self.assertEqual((count["to"], count["unit"], count["label"], count["ms"]), (64000, "K", "", [600, 1100]))

    def test_type_and_mark_with_glitch(self):
        steps, errors = ops("Trust? <type human>y</type>\n<mark door>open</mark>\n@glitch door | shut | frames=6")
        self.assertEqual(errors, [])
        self.assertEqual(steps[1]["op"], "type")
        self.assertTrue(steps[1]["human"])
        marked = [s for s in steps if s["op"] == "text" and s.get("id") == "door"]
        self.assertEqual([m["value"] for m in marked], ["open"])
        glitch = [s for s in steps if s["op"] == "glitch"][0]
        self.assertEqual((glitch["id"], glitch["to"], glitch["frames"]), ("door", "shut", 6))

    def test_bad_attributes_are_errors_of_their_line(self):
        _, errors = ops("ok\n<count to=x/>\n<count to=5 ms=fast/>")
        self.assertEqual([n for n, _ in errors], [2, 3])


class StepTests(SimpleTestCase):
    def test_task_bar_count_wait_and_effects(self):
        steps, errors = ops(
            "@task resolving  {host} | OK | 200-450\n@task auth | FAIL\n@bar key exchange | 700-1300 | width=20\n"
            "@count sending | 512 | KB | 800-1400 | result=OK\n@wait 450\n@read\n@cut\n@flash\n@clear\n@blank 2",
            {"host": "core"},
        )
        self.assertEqual(errors, [])
        self.assertEqual(steps[0]["op"], "dots")
        self.assertEqual((steps[0]["label"], steps[0]["status"], steps[0]["ms"]), ("resolving  core ", "OK", [200, 450]))
        self.assertEqual(steps[2]["status"], "FAIL")
        bar = [s for s in steps if s["op"] == "bar"][0]
        self.assertEqual((bar["label"], bar["width"]), ("key exchange ", 20))
        self.assertIn("count", kinds(steps))
        self.assertEqual(kinds(steps).count("newline"), 6)
        for op in ("wait", "read", "cut", "flash", "clear"):
            self.assertIn(op, kinds(steps))

    def test_bars_log_burst_countdown(self):
        steps, errors = ops(
            "@bars width=10\n  part 1 | 800-1200 | OK\n  part 2 | 600 | FAIL | 40\n"
            "@log 0.5 | rf | carrier up\n"
            "@burst gap=5-20\n  <dim>one</dim>\n  two\n"
            "@countdown Auto in {n}s... | 3"
        )
        self.assertEqual(errors, [])
        bars = [s for s in steps if s["op"] == "bars"][0]
        self.assertEqual([(r["label"], r["status"], r["stop"]) for r in bars["rows"]], [("part 1", "OK", 100), ("part 2", "FAIL", 40)])
        self.assertEqual(bars["width"], 10)
        self.assertTrue(any("carrier up" in s["value"] for s in steps if s["op"] == "text"))
        waits = [s["ms"] for s in steps if s["op"] == "wait"]
        self.assertIn([5, 20], waits)
        self.assertEqual([s for s in steps if s["op"] == "countdown"][0]["template"], "Auto in {n}s...")

    def test_unknown_steps_and_bad_values_name_the_line(self):
        _, errors = ops("ok\n@nope\n@wait soon\n@task\n@bars\n@bar x | 1 | stray")
        self.assertEqual([n for n, _ in errors], [2, 3, 4, 5, 6])

    def test_since_and_rand_work_in_lines_and_steps(self):
        steps, errors = ops("<since>2027-10-29</since> d\n@task silent <since>2027-10-29 | years</since> y | OK")
        self.assertEqual(errors, [])
        self.assertEqual(steps[0]["value"], "1,112 d")
        self.assertEqual(steps[2]["label"], "silent 3 y ")

    def test_unknown_parameter_is_an_error(self):
        self.assertEqual([n for n, _ in check_script("{nope}\n@task {nope2} | OK", ["host"])], [1, 2])


class IncludeTests(SimpleTestCase):
    LIBRARY = {"reach": "@task resolving {host} | OK | 100\n@task carrier | OK | 100", "loop": "@include loop"}

    def test_include_pastes_another_scene_with_the_same_parameters(self):
        steps, errors = ops("~ start\n@include reach\ndone", {"host": "core"}, self.LIBRARY.get)
        self.assertEqual(errors, [])
        self.assertEqual([s["label"] for s in steps if s["op"] == "dots"], ["resolving core ", "carrier "])

    def test_missing_and_circular_includes_are_errors(self):
        _, errors = ops("@include ghost\n@include loop", {}, self.LIBRARY.get)
        self.assertEqual([n for n, _ in errors], [1, 2])
        self.assertIn("по кругу", errors[1][1])
