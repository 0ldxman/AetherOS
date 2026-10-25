"""Сборщик консольных сцен: шаги, проверки, вложенность.

Запуск: python manage.py test console
"""
import json

from django.test import SimpleTestCase

from console.scene import Option, Scene, SceneError


def ops(scene):
    return [step["op"] for step in scene.to_dict()]


class OutputTests(SimpleTestCase):
    def test_say_is_text_plus_newline(self):
        steps = Scene().say("hello", style="dim").to_dict()
        self.assertEqual(steps, [{"op": "text", "value": "hello", "style": "dim"}, {"op": "newline"}])

    def test_say_parts_have_their_own_style_and_id(self):
        steps = Scene().say("a ", ("b", "success"), ("c", None, "name"), style="dim").to_dict()
        texts = [s for s in steps if s["op"] == "text"]
        self.assertEqual([s.get("style") for s in texts], ["dim", "success", "dim"])
        self.assertEqual(texts[2]["id"], "name")

    def test_say_can_leave_the_line_open(self):
        self.assertEqual(ops(Scene().say("a", end=False)), ["text"])

    def test_say_alone_ends_an_open_line(self):
        self.assertEqual(ops(Scene().say()), ["newline"])

    def test_blank_count(self):
        self.assertEqual(len(Scene().blank(3).to_dict()), 3)

    def test_row_pads_the_label_and_adds_a_dim_note(self):
        steps = Scene().row("node", "aether-main", note="(saved)", id="host").to_dict()
        self.assertEqual(steps[0]["value"], "node".ljust(10))
        self.assertEqual(steps[1], {"op": "text", "value": "aether-main", "id": "host"})
        self.assertEqual((steps[2]["value"], steps[2]["style"]), ("  (saved)", "dim"))
        self.assertEqual(steps[-1], {"op": "newline"})

    def test_type_defaults_flags_and_it_ends_the_line(self):
        scene = Scene().type("y", human=True, typo=True)
        step = scene.to_dict()[0]
        self.assertEqual((step["human"], step["typo"], step["speed"], step["chunk"]), (True, True, 22, 1))
        self.assertEqual(ops(scene), ["type", "newline"])

    def test_type_after_an_open_line_is_the_player_answering(self):
        scene = Scene().say("Trust? [y/n] ", end=False).type("y", human=True)
        self.assertEqual(ops(scene), ["text", "type", "newline"])

    def test_type_can_come_in_chunks_and_keep_the_line_open(self):
        scene = Scene().type("0123456789", chunk=4, end=False)
        self.assertEqual(ops(scene), ["type"])
        self.assertEqual(scene.to_dict()[0]["chunk"], 4)

    def test_chaining_returns_the_scene(self):
        scene = Scene()
        self.assertIs(scene.say("a", end=False).wait(10).flash().clear().cut(), scene)


class ProcessTests(SimpleTestCase):
    def test_dots_task_is_the_default_and_takes_the_color_of_its_result(self):
        scene = Scene().task("resolving", "OK", ms=700)
        step = scene.to_dict()[0]
        self.assertEqual((step["op"], step["label"], step["status"], step["style"], step["ms"]), ("dots", "resolving", "OK", "success", 700))
        self.assertEqual(ops(scene), ["dots", "newline"])

    def test_results_have_colors_and_custom_text_is_plain_unless_styled(self):
        styles = [Scene().task("a", r).to_dict()[0]["style"] for r in ("OK", "WARN", "FAIL", "10.40.7.12")]
        self.assertEqual(styles, ["success", "warning", "error", None])
        self.assertEqual(Scene().task("a", "10.40.7.12", style="dim").to_dict()[0]["style"], "dim")

    def test_task_note_is_dim_and_stays_on_the_line(self):
        steps = Scene().task("a", "OK", "(ECC)").to_dict()
        self.assertEqual([s["op"] for s in steps], ["dots", "text", "newline"])
        self.assertEqual((steps[1]["value"], steps[1]["style"]), ("  (ECC)", "dim"))

    def test_unit_task_waits_and_is_replaced_by_the_result(self):
        step = Scene().task("keyagent  starting", "OK", look="unit", done="keyagent  secure key agent").to_dict()[0]
        self.assertEqual(step["op"], "spin")
        self.assertEqual(step["pending"], [["[  ..  ] keyagent  starting", "dim"]])
        self.assertEqual(step["done"], [["[  up  ] ", "success"], ["keyagent  secure key agent", None]])

    def test_failed_and_warned_units_color_their_text_too(self):
        warn = Scene().task("a", "WARN", look="unit", done="b").to_dict()[0]["done"]
        fail = Scene().task("a", "FAIL", "(code 1)", look="unit", done="b").to_dict()[0]["done"]
        self.assertEqual(warn, [["[ warn ] ", "warning"], ["b", "warning"]])
        self.assertEqual(fail[0], ["[ fail ] ", "error"])
        self.assertEqual(fail[-1], ["(code 1)", "dim"])

    def test_the_old_systemd_marks_are_gone(self):
        text = json.dumps(Scene().task("a", "OK", look="unit").to_dict())
        for word in ("WAIT", "FAILED", "  OK  "):
            self.assertNotIn(word, text)

    def test_kernel_task_shows_an_unknown_time_then_the_real_one(self):
        step = Scene().task("vault: unlocking", "OK", at=0.801544).to_dict()[0]
        self.assertEqual(step["op"], "spin")
        self.assertIn("X.XXXXXX", step["pending"][0][0])
        self.assertEqual(step["done"][0][0], "  0.801544  vault: unlocking ")
        self.assertEqual(step["ms"], 801)

    def test_kernel_clock_runs_across_log_and_task(self):
        scene = Scene()
        scene.log(0.5, "cpu", "a")
        scene.task("b", "OK", at=1.0)
        waits = [s["ms"] for s in scene.to_dict() if s["op"] == "wait"]
        spin = [s for s in scene.to_dict() if s["op"] == "spin"][0]
        self.assertEqual(waits, [500])
        self.assertEqual(spin["ms"], 500)

    def test_unknown_task_look_is_refused(self):
        with self.assertRaises(SceneError):
            Scene().task("a", "OK", look="rainbow")

    def test_bar_ends_the_line(self):
        scene = Scene().bar("session ", ms=900, width=20)
        self.assertEqual(ops(scene), ["bar", "newline"])
        self.assertEqual((scene.to_dict()[0]["ms"], scene.to_dict()[0]["width"]), (900, 20))

    def test_count_pads_the_label_and_can_finish_with_a_result(self):
        steps = Scene().count("Memory Testing:", 64000, unit="K", result="OK", note="(ECC)").to_dict()
        self.assertEqual(steps[0]["label"], "Memory Testing:".ljust(17))
        self.assertEqual((steps[0]["to"], steps[0]["unit"]), (64000, "K"))
        self.assertEqual((steps[1]["value"], steps[1]["style"]), (" OK", "success"))

    def test_countdown_template_keeps_its_placeholder(self):
        step = Scene().countdown("Auto-boot in {n}s...", 3).to_dict()[0]
        self.assertEqual((step["template"], step["seconds"]), ("Auto-boot in {n}s...", 3))

    def test_countdown_needs_a_whole_positive_number(self):
        for bad in (0, -1, 1.5, "3", True):
            with self.assertRaises(SceneError, msg=repr(bad)):
                Scene().countdown("{n}", bad)


class RealismTests(SimpleTestCase):
    def test_log_line_is_time_subsystem_text_with_the_subsystem_dimmed(self):
        steps = Scene().log(0.004211, "cpu", "8 cores").to_dict()
        texts = [s for s in steps if s["op"] == "text"]
        self.assertEqual(texts[0]["value"], "  0.004211")
        self.assertEqual((texts[2]["value"], texts[2]["style"]), ("cpu    ", "dim"))
        self.assertEqual(texts[3]["value"], " 8 cores")

    def test_burst_prints_lines_together_with_short_random_gaps(self):
        scene = Scene().burst("a", ("b ", ("c", "dim")), gap=(5, 20))
        self.assertEqual(ops(scene).count("newline"), 2)
        waits = [s["ms"] for s in scene.to_dict() if s["op"] == "wait"]
        self.assertEqual(waits, [[5, 20], [5, 20]])

    def test_a_part_tuple_is_one_part_not_a_list_of_lines(self):
        scene = Scene().burst(("done", "success"))
        self.assertEqual(ops(scene).count("newline"), 1)

    def test_times_can_be_ranges_so_two_boots_differ(self):
        scene = Scene().wait((100, 300)).task("a", "OK", ms=(500, 900)).bar("b", ms=(800, 1200))
        steps = {s["op"]: s["ms"] for s in scene.to_dict() if "ms" in s}
        self.assertEqual(steps, {"wait": [100, 300], "dots": [500, 900], "bar": [800, 1200]})

    def test_a_range_must_be_ordered(self):
        with self.assertRaises(SceneError):
            Scene().wait((300, 100))

    def test_the_cursor_is_shown_only_where_the_console_waits_for_input(self):
        plain = Scene().say("working", end=False).to_dict()[-1]
        prompt = Scene().say("Trust? [y/n] ", end=False, cursor=True).to_dict()[-1]
        self.assertNotIn("cursor", plain)
        self.assertTrue(prompt["cursor"])

    def test_cut_is_a_mode_change_not_a_fade(self):
        self.assertEqual(Scene().cut().to_dict(), [{"op": "cut"}])
        self.assertFalse(hasattr(Scene(), "fade"))


class EffectTests(SimpleTestCase):
    def test_glitch_and_mask(self):
        step = Scene().glitch("host", "aether-null").to_dict()[0]
        self.assertEqual((step["op"], step["id"], step["to"], step["frames"]), ("glitch", "host", "aether-null", 14))
        self.assertEqual(Scene().glitch("host", "x", frames=26).to_dict()[0]["frames"], 26)
        self.assertEqual(Scene.mask(4), "████")



class ValidationTests(SimpleTestCase):
    def test_unknown_style_is_refused(self):
        with self.assertRaises(SceneError):
            Scene().say("x", style="rainbow")

    def test_wait_must_be_a_sensible_number(self):
        for bad in (-1, "10", None, 10**9, True):
            with self.assertRaises(SceneError, msg=repr(bad)):
                Scene().wait(bad)

    def test_one_of_needs_variants(self):
        with self.assertRaises(SceneError):
            Scene().one_of()

    def test_choice_needs_options(self):
        with self.assertRaises(SceneError):
            Scene().choice("x", [])

    def test_delay_range_must_be_ordered(self):
        with self.assertRaises(SceneError):
            Option("a", "a", "x", appear=(30, 20)).to_dict()

    def test_retype_needs_at_least_two_texts(self):
        with self.assertRaises(SceneError):
            Option("a", "a", "x", appear=100, retype=("only one",)).to_dict()

    def test_retype_needs_appear(self):
        with self.assertRaises(SceneError):
            Option("a", "a", "x", retype=("one", "two")).to_dict()


class BranchingTests(SimpleTestCase):
    def test_one_of_nests_scenes(self):
        step = Scene().one_of(Scene().say("a", end=False), Scene().say("b", end=False)).to_dict()[0]
        self.assertEqual([s[0]["value"] for s in step["scenes"]], ["a", "b"])

    def test_plain_option_shows_its_key_and_has_no_late_or_rewrites(self):
        data = Option("discord", "D", "external authority", tag="DISCORD").to_dict()
        self.assertEqual((data["key"], data["keys"]), ("[ D ]", ["d"]))
        self.assertNotIn("late", data)
        self.assertNotIn("rewrites", data)

    def test_late_option_that_retypes_itself(self):
        data = Option(
            "bypass", "?", ["a", "b"], also=("/",), style="warning",
            appear=2200, typo=False, settle=300,
            retype=("x", "y"), retype_after=(20000, 30000),
        ).to_dict()
        self.assertEqual(data["key"], "[ ? ]")
        self.assertEqual(data["keys"], ["?", "/"])
        self.assertEqual(data["label"], ["a", "b"])
        self.assertEqual(data["late"], {"after_ms": 2200, "typo": False, "settle_ms": 300})
        self.assertEqual(data["rewrites"], {"after_ms": [20000, 30000], "labels": ["x", "y"]})

    def test_late_defaults(self):
        late = Option("a", "a", "x", appear=0).to_dict()["late"]
        self.assertEqual((late["after_ms"], late["typo"], late["settle_ms"]), (0, True, 500))

    def test_choice_carries_its_options(self):
        scene = Scene().choice("entry", [Option("a", "a", "x"), Option("b", "b", "y", appear=10)])
        step = scene.to_dict()[0]
        self.assertEqual([o["id"] for o in step["options"]], ["a", "b"])

    def test_the_whole_scene_is_json(self):
        scene = Scene().say("é ·", style="dim").choice("c", [Option("a", "a", "x")])
        self.assertEqual(json.loads(scene.to_json()), scene.to_dict())
        self.assertIn("é ·", scene.to_json())  # без \u-экранирования, читаемо в исходнике
