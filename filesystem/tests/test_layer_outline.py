"""Конструктор слоёв: текст стека разбирается в структуру и собирается обратно без потерь.

Запуск: python manage.py test filesystem.tests.test_layer_outline
"""
from django.test import SimpleTestCase

from filesystem.layers.outline import OutlineLayer, build, catalog, outline
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
