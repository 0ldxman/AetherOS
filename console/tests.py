"""Сборщик консольных сцен: шаги, проверки, вложенность.

Запуск: python manage.py test console
"""
import json

from django.test import SimpleTestCase

from console.scene import Option, Scene, SceneError


class BuildingTests(SimpleTestCase):
    def test_line_is_text_plus_newline(self):
        steps = Scene().line("hello", style="dim").to_dict()
        self.assertEqual(steps, [{"op": "text", "value": "hello", "style": "dim"}, {"op": "newline"}])

    def test_line_with_mixed_styles(self):
        steps = Scene().line("a ", ("b", "success")).to_dict()
        self.assertEqual([s.get("style") for s in steps if s["op"] == "text"], [None, "success"])

    def test_empty_line_still_ends_the_line(self):
        self.assertEqual(Scene().line().to_dict()[-1], {"op": "newline"})

    def test_kv_pads_the_label_and_adds_a_dim_note(self):
        steps = Scene().kv("node", "aether-main", note="(saved)", id="host").to_dict()
        self.assertEqual(steps[0]["value"], "node".ljust(10))
        self.assertEqual(steps[1], {"op": "text", "value": "aether-main", "id": "host"})
        self.assertEqual((steps[2]["value"], steps[2]["style"]), ("  (saved)", "dim"))

    def test_newline_count(self):
        self.assertEqual(len(Scene().newline(3).to_dict()), 3)

    def test_chaining_returns_the_scene(self):
        scene = Scene()
        self.assertIs(scene.text("a").pause(10).flash().clear(), scene)

    def test_type_defaults_and_human_flags(self):
        step = Scene().type("y", human=True, typo=True).to_dict()[0]
        self.assertEqual((step["human"], step["typo"], step["speed"]), (True, True, 22))

    def test_dots(self):
        step = Scene().dots("resolving", "OK", ms=700).to_dict()[0]
        self.assertEqual((step["label"], step["status"], step["style"], step["ms"]), ("resolving", "OK", "success", 700))

    def test_dots_end_the_line_unless_told_otherwise(self):
        self.assertEqual([s["op"] for s in Scene().dots("a", "OK").to_dict()], ["dots", "newline"])
        self.assertEqual([s["op"] for s in Scene().dots("a", "OK", newline=False).to_dict()], ["dots"])

    def test_route_has_a_timeout_hop(self):
        scene = Scene().route([("relay 01", "VX-04", 12), ("relay 02", "···", None)])
        text = "".join(s.get("value", "") for s in scene.to_dict() if s["op"] == "text")
        self.assertIn("12 ms", text)
        self.assertIn("no answer", text)
        self.assertEqual(sum(1 for s in scene.to_dict() if s["op"] == "pause"), 2)

    def test_glitch_and_mask(self):
        step = Scene().glitch("host", "aether-null").to_dict()[0]
        self.assertEqual((step["op"], step["id"], step["to"], step["frames"]), ("glitch", "host", "aether-null", 14))
        self.assertEqual(Scene().glitch("host", "x", frames=26).to_dict()[0]["frames"], 26)
        self.assertEqual(Scene.mask(4), "████")

    def test_progress_bar_ends_the_line(self):
        steps = Scene().progress("session ", ms=900, width=20).to_dict()
        self.assertEqual([s["op"] for s in steps], ["progress", "newline"])
        self.assertEqual((steps[0]["ms"], steps[0]["width"]), (900, 20))

    def test_extend_appends_steps(self):
        self.assertEqual(len(Scene().text("a").extend(Scene().text("b")).to_dict()), 2)


class ValidationTests(SimpleTestCase):
    def test_unknown_style_is_refused(self):
        with self.assertRaises(SceneError):
            Scene().text("x", "rainbow")

    def test_pause_must_be_a_sensible_number(self):
        for bad in (-1, "10", None, 10**9, True):
            with self.assertRaises(SceneError, msg=repr(bad)):
                Scene().pause(bad)

    def test_one_of_needs_variants(self):
        with self.assertRaises(SceneError):
            Scene().one_of()

    def test_choice_needs_options(self):
        with self.assertRaises(SceneError):
            Scene().choice("x", [])

    def test_delay_range_must_be_ordered(self):
        with self.assertRaises(SceneError):
            Option("a", "[ A ]", "x", late={"after_ms": [30, 20]}).to_dict()

    def test_rewrites_need_at_least_two_texts(self):
        with self.assertRaises(SceneError):
            Option("a", "[ A ]", "x", rewrites={"labels": ["only one"]}).to_dict()


class BranchingTests(SimpleTestCase):
    def test_one_of_nests_scenes(self):
        step = Scene().one_of(Scene().text("a"), Scene().text("b")).to_dict()[0]
        self.assertEqual([s[0]["value"] for s in step["scenes"]], ["a", "b"])

    def test_plain_option_has_no_late_or_rewrites(self):
        data = Option("discord", "[ D ]", "external authority", tag="DISCORD", keys=("D",)).to_dict()
        self.assertEqual(data["keys"], ["d"])
        self.assertNotIn("late", data)
        self.assertNotIn("rewrites", data)

    def test_late_option_that_rewrites_itself(self):
        option = Option(
            "bypass", "[ ? ]", ["a", "b"], keys=("?", "/"), style="warning",
            late={"after_ms": 2200, "typo": False, "settle_ms": 300},
            rewrites={"after_ms": [20000, 30000], "labels": ["x", "y"]},
        )
        data = option.to_dict()
        self.assertEqual(data["label"], ["a", "b"])
        self.assertEqual(data["late"], {"after_ms": 2200, "typo": False, "settle_ms": 300})
        self.assertEqual(data["rewrites"], {"after_ms": [20000, 30000], "labels": ["x", "y"]})

    def test_late_defaults(self):
        late = Option("a", "[ A ]", "x", late={}).to_dict()["late"]
        self.assertEqual((late["after_ms"], late["typo"], late["settle_ms"]), (0, True, 450))

    def test_choice_carries_its_options(self):
        scene = Scene().choice("entry", [Option("a", "[ A ]", "x"), Option("b", "[ B ]", "y", late={"after_ms": 10})])
        step = scene.to_dict()[0]
        self.assertEqual([o["id"] for o in step["options"]], ["a", "b"])
        self.assertNotIn("events", step)

    def test_the_whole_scene_is_json(self):
        scene = Scene().line("é ·", style="dim").choice("c", [Option("a", "[ A ]", "x")])
        self.assertEqual(json.loads(scene.to_json()), scene.to_dict())
        self.assertIn("é ·", scene.to_json())  # без \u-экранирования, читаемо в исходнике
