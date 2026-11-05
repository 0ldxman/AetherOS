"""Конструктор слоёв: текст стека разбирается в структуру и собирается обратно без потерь.

Запуск: python manage.py test filesystem.tests.test_layer_outline
"""
from django.test import SimpleTestCase

from filesystem.layers.hooks import ACTIONS, EVENTS
from filesystem.layers.outline import (
    ACTION_TITLES, EVENT_TITLES, Action, Answer, Hook, OutlineLayer, build, catalog, hooks_catalog, outline, regen_body, steps, structure_of,
)
from filesystem.layers.parser import parse, tokenize

SAMPLES = [
    "",
    "> corrupted",
    "> encrypted hunter2 attempts=3",
    '> encrypted "pass word" key=cardkey attempts=5 -> locked.bin',
    "# комментарий до слоёв\n\n> encrypted hunter2\nfile: Header checksum mismatch\non remove:\n- say \"Готово\"\n- add damaged\non fail: say \"Не то\"\n\n> shifted skip=4 out=data.bin\n# заметка слоя\nstrings: \"многострочный\n> текст в кавычках\"",
    "> binary utf16\n> disguised jpg => copy.jpg",
]


def shape(text):
    """Что видит движок: слои без номеров строк."""
    layers, problems = parse(text)
    assert not problems, problems
    return [
        (l.name, [(a.key, a.value) for a in l.args], l.move and (l.move.kind, l.move.target),
         {k: (o.command, o.text) for k, o in l.overrides.items()}, [(h.event, [(a.name, a.value) for a in h.actions]) for h in l.hooks])
        for l in layers
    ]


class OutlineTests(SimpleTestCase):
    def test_every_sample_survives_the_round_trip(self):
        for text in SAMPLES:
            found = outline(text)
            self.assertTrue(found.editable, text)
            again = build(found.preamble, found.layers)
            self.assertEqual(shape(again), shape(text), text)
            second = outline(again)
            self.assertEqual(build(second.preamble, second.layers), again, "сборка устойчива: второй проход ничего не меняет")

    def test_bodies_comments_and_the_preamble_are_kept_verbatim(self):
        found = outline(SAMPLES[4])
        self.assertEqual(found.preamble, "# комментарий до слоёв")
        self.assertEqual([l.name for l in found.layers], ["encrypted", "shifted"])
        self.assertIn('on fail: say "Не то"', found.layers[0].body)
        self.assertTrue(found.layers[1].body.startswith("# заметка слоя"))
        self.assertIn("> текст в кавычках", found.layers[1].body)         # строка с «>» внутри кавычек не стала слоем

    def test_values_go_to_params_and_the_move_is_kept(self):
        row = outline('> encrypted "pass word" key=cardkey attempts=5 -> locked.bin').layers[0]
        self.assertEqual(row.values, {"password": "pass word", "key": "cardkey", "attempts": "5"})
        self.assertEqual(row.move, ("rename", "locked.bin"))

    def test_editing_a_value_changes_only_the_header(self):
        found = outline(SAMPLES[4])
        found.layers[0].values["attempts"] = "7"
        text = build(found.preamble, found.layers)
        self.assertIn("> encrypted hunter2 attempts=7", text)
        self.assertIn('on fail: say "Не то"', text)
        self.assertIn("# комментарий до слоёв", text)

    def test_tricky_values_are_quoted_so_they_read_back_the_same(self):
        for value in ["a b", 'say "hi"', "a=b", "back\\slash", "->", "=>", "#x"]:
            text = build("", [OutlineLayer("encrypted", {"password": value, "key": value})])
            args, error = tokenize(text.split(" ", 2)[2])
            self.assertIsNone(error, value)
            self.assertEqual(outline(text).layers[0].values, {"password": value, "key": value}, value)

    def test_empty_values_are_left_out(self):
        self.assertEqual(build("", [OutlineLayer("encrypted", {"password": "", "attempts": " "})]), "> encrypted")

    def test_what_the_constructor_cannot_edit_is_said_aloud(self):
        self.assertIn("нет в каталоге", outline("> mystery 1").unsupported)
        self.assertIn("неизвестный", outline("> encrypted pw colour=red").unsupported)
        self.assertIn("лишний", outline("> corrupted extra").unsupported)
        broken = outline("> encrypted pw\nнепонятная строка")
        self.assertTrue(broken.problems)
        self.assertFalse(broken.editable)

    def test_the_catalog_describes_every_layer_with_a_title(self):
        rows = {row["name"]: row for row in catalog()}
        self.assertEqual(set(rows), {"corrupted", "damaged", "encrypted", "shifted", "binary", "disguised"})
        self.assertTrue(all(row["title"] and row["title"] != row["name"] for row in rows.values()))
        password = next(p for p in rows["encrypted"]["params"] if p["name"] == "password")
        self.assertEqual((password["positional"], password["type"], password["label"]), (True, "str", "Пароль"))
        attempts = next(p for p in rows["encrypted"]["params"] if p["name"] == "attempts")
        self.assertEqual((attempts["type"], attempts["default"]), ("int", "3"))


BODY = """file: Header checksum mismatch
strings: "первая строка
вторая"
on remove:
- say "Готово: {attempts_left}"
- drop /home/a.dat
- mail door_open delay=30
on fail: add damaged
on read:
- kick
"""


class BodyTests(SimpleTestCase):
    def test_answers_and_hooks_are_read_from_the_body(self):
        answers, hooks = structure_of(BODY)
        self.assertEqual([(a.command, a.text) for a in answers], [("file", "Header checksum mismatch"), ("strings", "первая строка\nвторая")])
        self.assertEqual([h.event for h in hooks], ["remove", "fail", "read"])
        self.assertEqual([(a.name, a.value) for a in hooks[0].actions], [("say", "Готово: {attempts_left}"), ("drop", "/home/a.dat"), ("mail", "door_open delay=30")])
        self.assertEqual([(a.name, a.value) for a in hooks[2].actions], [("kick", "")])

    def test_regenerating_gives_the_same_meaning(self):
        answers, hooks = structure_of(BODY)
        again = structure_of(regen_body(answers, hooks))
        self.assertEqual(again, (answers, hooks))
        self.assertEqual(regen_body(*again), regen_body(answers, hooks), "второй проход ничего не меняет")

    def test_a_body_with_comments_is_left_to_the_text_editor(self):
        self.assertIsNone(structure_of("# заметка\nfile: текст"))
        self.assertIsNone(structure_of("непонятная строка"))
        found = outline("> encrypted hunter2\n# заметка\nfile: текст")
        self.assertIsNone(found.layers[0].answers)
        self.assertIn("# заметка", build(found.preamble, found.layers))        # тело не тронуто

    def test_an_untouched_body_is_kept_exactly_and_an_edited_one_is_rebuilt(self):
        text = "> encrypted hunter2\n" + BODY.replace("on fail: add damaged", 'on fail: say "Не то"')
        found = outline(text)
        self.assertEqual(build(found.preamble, found.layers), text.rstrip("\n"))
        found.layers[0].hooks[0].actions.append(Action("say", "Ещё"))
        rebuilt = build(found.preamble, found.layers)
        self.assertIn('- say "Ещё"', rebuilt)
        self.assertEqual(structure_of(outline(rebuilt).layers[0].body)[1][0].actions[-1].value, "Ещё")

    def test_adding_answers_and_hooks_from_nothing(self):
        layer = OutlineLayer("encrypted", {"password": "pw"}, answers=[Answer("ftyp", "Зашифровано")], hooks=[Hook("fail", [Action("add", "damaged"), Action("say", 'Ты "почти" смог')])])
        text = build("", [layer])
        self.assertEqual(text, '> encrypted pw\nftyp: Зашифровано\non fail:\n- add damaged\n- say "Ты \\"почти\\" смог"')
        back = outline(text).layers[0]
        self.assertEqual(back.hooks[0].actions[1].value, 'Ты "почти" смог')

    def test_multiline_and_awkward_answers_come_back_exactly(self):
        for text in ["строка\nвторая", ' "в кавычках" ', "  пробелы по краям  ", '"начинается с кавычки', "обратный \\ слэш"]:
            parts = structure_of(regen_body([Answer("file", text)], []))
            self.assertIsNotNone(parts, text)
            self.assertEqual(parts[0][0].text, text)

    def test_the_hook_catalog_describes_every_event_and_action(self):
        self.assertEqual(set(EVENT_TITLES), set(EVENTS))
        self.assertEqual(set(ACTION_TITLES), set(ACTIONS))
        info = hooks_catalog()
        self.assertEqual([e["name"] for e in info["events"]], list(EVENTS))
        kick = next(a for a in info["actions"] if a["name"] == "kick")
        self.assertEqual(kick["value_label"], "")
        say = next(a for a in info["actions"] if a["name"] == "say")
        self.assertTrue(say["text"])
        self.assertIn("ftyp", info["commands"])


class StepsTests(SimpleTestCase):
    def test_every_layer_says_how_the_player_removes_it(self):
        rows = steps([
            OutlineLayer("encrypted", {"password": "hunter2"}),
            OutlineLayer("encrypted", {"key": "cardkey", "password": "pw"}),
            OutlineLayer("shifted", {"skip": "4", "count": "2"}),
            OutlineLayer("binary", {"encoding": "utf16"}),
            OutlineLayer("disguised", {"format": ".jpg"}),
            OutlineLayer("damaged", {}),
        ])
        self.assertEqual(rows, [
            "ward <файл> hunter2", "ward -k cardkey <файл> или ward <файл> pw", "blk <файл> skip=4 count=2",
            "cvt enc utf16 <файл>", "cvt ext <файл> <файл.jpg>", "rpr <файл>",
        ])

    def test_nothing_is_promised_while_the_values_are_missing(self):
        self.assertEqual(steps([OutlineLayer("encrypted", {}), OutlineLayer("shifted", {}), OutlineLayer("corrupted", {}), OutlineLayer("binary", {"encoding": " "})]), ["", "", "", ""])
