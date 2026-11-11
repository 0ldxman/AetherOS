"""Сценарий переписки как документ редактора: выгрузка, сохранение, проверка, песочница; и API Студии поверх них.

Запуск: python manage.py test mail.tests.test_authoring
"""
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.models import Item
from mail import authoring, letters, talk
from mail.models import Conversation, Persona, Step, Variant
from team.testing import full_role


def _doc(**steps):
    return {"title": "Dock", "slug": "dock", "note": "", "persona": None, "steps": [{"name": name, **data} for name, data in steps.items()]}


class DocumentTests(TestCase):
    def setUp(self):
        self.guard = Persona.objects.create(address="guard@core")
        self.talk = authoring.create(self.guard, "Dock", "dock")

    def doc(self, steps):
        return {"title": "Dock", "slug": "dock", "note": "", "persona": self.guard.pk, "steps": steps}

    def test_new_conversation_has_a_start_step_and_lays_out(self):
        doc = authoring.export(self.talk)
        self.assertEqual([s["name"] for s in doc["steps"]], ["start"])
        self.assertEqual((doc["steps"][0]["x"], doc["steps"][0]["y"]), (0.0, 0.0))

    def test_save_writes_steps_variants_letters_and_outcomes(self):
        authoring.save(self.talk, self.doc([
            {"name": "hello", "opening": True, "x": 10, "y": 20, "variants": [
                {"title": "Ask", "text": "Code {{4711}}, dock [[7|9]].", "condition": "pass and not alarm", "need_flags": ["met", " "],
                 "max_attempts": 2, "outcomes": {"word:7": [{"do": "goto", "step": "open"}],
                                                 "wrong": [{"do": "letter", "subject": "No", "text": "Wrong code.", "delay": "5"}]}}]},
            {"name": "open", "letter": {"subject": "Granted", "text": "Gate open."}},
        ]))
        steps = list(self.talk.steps.all())
        self.assertEqual([(s.name, s.opening, s.x) for s in steps], [("hello", True, 10.0), ("open", False, 0.0)])
        letter = letters.parse(steps[1].letter.body)
        self.assertEqual((letter.sender, letter.subject, letter.body.strip()), ("guard@core", "Granted", "Gate open."))
        variant = steps[0].variants.get()
        self.assertEqual(variant.condition, {"all": ["pass", {"not": "alarm"}]})
        self.assertEqual(variant.need_flags, ["met"])
        wrong = variant.outcomes["wrong"][0]
        self.assertEqual((wrong["do"], wrong["delay"], set(wrong)), ("letter", 5, {"do", "item", "delay"}))
        self.assertEqual(letters.parse(Item.objects.get(slug=wrong["item"]).body).subject, "No")

        doc = authoring.export(self.talk)                          # обратно в редактор: условие текстом, письма темой и текстом
        hello = doc["steps"][0]["variants"][0]
        self.assertEqual(hello["condition"], "pass and not alarm")
        self.assertEqual((hello["outcomes"]["wrong"][0]["subject"], hello["outcomes"]["wrong"][0]["text"]), ("No", "Wrong code."))
        self.assertEqual(doc["steps"][1]["letter"]["subject"], "Granted")

    def test_resave_keeps_ids_renames_swap_and_drops_missing(self):
        authoring.save(self.talk, self.doc([{"name": "a", "variants": [{"title": "1"}, {"title": "2"}]}, {"name": "b"}, {"name": "c"}]))
        doc = authoring.export(self.talk)
        a, b, c = doc["steps"]
        a["name"], b["name"] = "b", "a"                              # поменять имена местами: уникальность не мешает
        a["variants"] = a["variants"][1:]
        authoring.save(self.talk, self.doc([a, b]))
        self.assertEqual(list(self.talk.steps.values_list("pk", "name")), [(a["id"], "b"), (b["id"], "a")])
        self.assertEqual(list(Variant.objects.filter(step__conversation=self.talk).values_list("title", flat=True)), ["2"])

    def test_editing_a_letter_keeps_a_foreign_sender_and_own_headers(self):
        item = Item.objects.create(slug="fake", name="fake.msg", format="msg", body="From: boss@hq\nTo: {to}\nSubject: Old\nX-Label: hq\n\nHi\n")
        authoring.save(self.talk, self.doc([{"name": "a", "letter": {"item": "fake", "subject": "New", "text": "Hello"}}]))
        item.refresh_from_db()
        parsed = letters.parse(item.body)
        self.assertEqual((parsed.sender, parsed.subject, parsed.get("X-Label"), parsed.body.strip()), ("boss@hq", "New", "hq", "Hello"))

    def test_broken_names_and_conditions_are_refused(self):
        with self.assertRaises(ValidationError):
            authoring.save(self.talk, self.doc([{"name": "a"}, {"name": "a"}]))
        with self.assertRaises(ValidationError):
            authoring.save(self.talk, self.doc([{"name": "a", "variants": [{"title": "x", "condition": "a and"}]}]))
        self.assertEqual(list(self.talk.steps.values_list("name", flat=True)), ["start"])

    def test_problems_name_what_is_wrong_and_where(self):
        found = authoring.problems(self.doc([
            {"name": "a", "variants": [{"title": "", "text": "{{}} [[x|y]]", "outcomes": {"word:z": [{"do": "goto", "step": "nowhere"}]}}]},
            {"name": "lost"},
        ]))
        texts = {(p["step"], p["text"]) for p in found}
        self.assertIn(("a", "У варианта нет подписи."), texts)
        self.assertIn(("a", "Пустой секрет {{}}."), texts)
        self.assertIn(("a", "Исход «word:z» никогда не сработает."), texts)
        self.assertIn(("a", "Переход на шаг «nowhere», которого нет."), texts)
        self.assertIn(("lost", "На этот шаг ничего не ведёт."), texts)

    def test_layout_puts_steps_in_columns_by_distance(self):
        steps = authoring.layout([
            {"name": "start", "variants": [{"outcomes": {"ok": [{"do": "goto", "step": "two"}]}}]},
            {"name": "two"}, {"name": "alone"},
        ])
        self.assertEqual([(s["name"], s["x"]) for s in steps], [("start", 0.0), ("two", 340.0), ("alone", 680.0)])


class SandboxTests(TestCase):
    variant = {"title": "Pass", "text": "Code {{4711}}, dock [[7|9]].", "max_attempts": 2,
               "outcomes": {"word:7": [{"do": "goto", "step": "open"}], "ok": [{"do": "flag", "name": "x"}],
                            "wrong": [{"do": "flag", "name": "bad"}], "exhausted": [{"do": "goto", "step": "closed"}]}}

    def test_words_win_over_ok_and_wrong_runs_out(self):
        run = lambda typed, used=0: authoring.trial([self.variant], pick=0, typed=typed, used=used)["result"]
        self.assertEqual(run("code 4711, dock 7.")["sockets"], ["word:7"])
        self.assertEqual(run("code 4711, dock 9.")["sockets"], ["ok"])
        self.assertEqual((run("code 1111, dock 9.")["kind"], run("code 1111, dock 9.")["left"]), ("wrong", 1))
        self.assertEqual(run("code 1111, dock 9.", used=1)["actions"], [{"do": "goto", "step": "closed"}])
        self.assertEqual(run("hello")["kind"], "mismatch")

    def test_offers_follow_keys_flags_and_closed_mode(self):
        variants = [{"title": "A", "condition": "pass"}, {"title": "B", "need_flags": ["met"], "closed": "hidden"}, {"title": "C", "text": "{{s}}"}]
        offers = authoring.trial(variants)["offers"]
        self.assertEqual([o["shown"] for o in offers], ["mystery", "hidden", "open"])
        self.assertEqual(offers[2]["layout"], [{"hidden": 1}])
        opened = authoring.trial(variants, keys=["pass"], flags=["met"], pick=1)
        self.assertEqual([o["shown"] for o in opened["offers"]], ["open", "open", "open"])
        self.assertEqual(authoring.trial(variants, pick=0)["result"]["kind"], "closed")

    def test_attachment_must_fit(self):
        Item.objects.create(slug="proof", name="proof.txt", format="txt", body="x")
        variant = {"title": "P", "attachment": {"kind": "item", "slug": "proof"}, "outcomes": {"ok": [{"do": "flag", "name": "x"}]}}
        self.assertEqual(authoring.trial([variant], pick=0)["result"]["kind"], "wrong")
        self.assertEqual(authoring.trial([variant], pick=0, attachment="proof")["result"]["kind"], "ok")

    def test_sockets_of_a_variant(self):
        self.assertEqual(talk.sockets("Dock [[7|9]]"), ["ok", "word:7", "word:9"])
        self.assertEqual(talk.sockets("{{x}}", max_attempts=3), ["ok", "wrong", "exhausted"])


@override_settings(FORCE_SCRIPT_NAME=None)
class StudioMailApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def call(self, method, path, body=None):
        response = getattr(self.client, method)("/studio/api/mail" + path, data=json.dumps(body) if body is not None else None,
                                                content_type="application/json")
        return response.status_code, (response.json() if response.content else None)

    def test_persona_conversation_save_check_and_try(self):
        status, persona = self.call("post", "/personas", {"address": "Guard@Core", "name": "Guard"})
        self.assertEqual((status, persona["address"]), (200, "guard@core"))
        self.assertEqual(self.call("post", "/personas", {"address": "guard@core"})[0], 400)
        status, row = self.call("post", "/conversations", {"persona": persona["id"], "title": "Dock", "slug": "dock"})
        self.assertEqual(status, 200)
        status, talk_ = self.call("get", f"/conversations/{row['id']}")
        doc = talk_["doc"]
        doc["steps"][0]["variants"] = [{"title": "Hi", "text": "Hi [[a|b]]", "outcomes": {"word:a": [{"do": "goto", "step": "start"}]}}]
        status, saved = self.call("put", f"/conversations/{row['id']}", doc)
        self.assertEqual((status, saved["doc"]["steps"][0]["variants"][0]["title"]), (200, "Hi"))
        self.assertEqual(self.call("post", "/check", doc)[1], [])
        status, trial = self.call("post", "/try", {"variants": doc["steps"][0]["variants"], "pick": 0, "typed": "hi a"})
        self.assertEqual((status, trial["result"]["sockets"]), (200, ["word:a"]))
        self.assertEqual(self.call("get", "")[1][0]["conversations"][0]["slug"], "dock")
        self.assertEqual(self.call("get", "/picks?kind=letter")[0], 200)
        self.assertEqual(self.call("delete", f"/conversations/{row['id']}")[0], 204)
        self.assertFalse(Conversation.objects.exists())
