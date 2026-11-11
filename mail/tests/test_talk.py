"""Переписка с персонажами: набор с секретами и выбором слова, шаги и исходы, попытки, новое письмо и возврат от
MAILER-DAEMON, письмо с чужой учётки, вложение-доказательство, пересылка, метки, ключи, хуки.

Запуск: python manage.py test mail
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from filesystem.models import Item, ItemSignature
from filesystem.testing import key_item, make_app, make_file
from machines.current import SESSION_KEY
from machines.models import Machine, MachineProfile, Session
from mail import talk
from mail.boxes import Box
from mail.delivery import deliver_by_slug
from mail.models import Conversation, Flag, Persona, Step, TalkState, Variant


class CheckTests(TestCase):
    def test_secret_choice_case_and_yo(self):
        template = "Код двери: {{4471}}. Груз на [[складе 7|складе 9]]. Всё."
        self.assertEqual(talk.check(template, "код двери: 4471. груз на складе 9. всё.").verdict, "ok")
        self.assertEqual(talk.check(template, "Код двери: 4471. Груз на складе 9. Всё.").words, ["складе 9"])
        self.assertEqual(talk.check(template, "Код двери: 1111. Груз на складе 7. Всё.").verdict, "wrong")
        self.assertEqual(talk.check(template, "Код двери: 4471. Груз на складе 8. Всё.").verdict, "mismatch")
        self.assertEqual(talk.check("Ещё {{ёж}}", "еще  ЕЖ").verdict, "ok")
        self.assertEqual(talk.public("Код {{4471}} [[a|b]]"), [{"text": "Код "}, {"hidden": 4}, {"text": " "}, {"choices": ["a", "b"]}])


def letter(slug, sender, subject, body=""):
    return Item.objects.create(slug=slug, name=slug, format="msg", body=f"From: {sender}\nTo: {{to}}\nSubject: {subject}\n\n{body}")


@override_settings(FORCE_SCRIPT_NAME=None)
class TalkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="intercom", icon="mail", path="/apps/mail/")
        make_file(cls.main, "/home/ivan/report.txt", body="отчёт")
        cls.ivan = User.objects.create_user("ivan", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.main, user=cls.ivan, name="Ivan", login="ivan", freq=1)
        cls.captain = MachineProfile.objects.create(machine=cls.main, name="Captain", login="captain", freq=2)

        cls.guard = Persona.objects.create(address="Guard@Port", name="Охрана порта")
        cls.talk = Conversation.objects.create(persona=cls.guard, slug="door", title="Код двери")
        cls.ask = letter("guard-ask", "guard@port", "Код?", "Назовите код двери.")
        cls.thanks = letter("guard-thanks", "guard@port", "Принято", "Проходите.")
        cls.warn = letter("guard-warn", "guard@port", "Неверно", "Это не тот код.")
        cls.angry = letter("guard-angry", "guard@port", "Хватит", "Я вызываю патруль.")
        cls.left7 = letter("guard-7", "guard@port", "Склад 7", "Седьмой открыт.")
        cls.first = Step.objects.create(conversation=cls.talk, name="ask", order=1, letter=cls.ask)
        cls.done = Step.objects.create(conversation=cls.talk, name="done", order=2, letter=cls.thanks)
        cls.lost = Step.objects.create(conversation=cls.talk, name="lost", order=3, letter=cls.angry)
        cls.code = Variant.objects.create(
            step=cls.first, title="Назвать код", text="Код: {{4471}}. Склад [[7|9]].", max_attempts=2,
            outcomes={"ok": [{"do": "goto", "step": "done"}, {"do": "flag", "name": "door-open"}],
                      "word:7": [{"do": "goto", "step": "done"}, {"do": "letter", "item": "guard-7"}],
                      "wrong": [{"do": "letter", "item": "guard-warn"}], "exhausted": [{"do": "goto", "step": "lost"}]},
        )
        Variant.objects.create(step=cls.first, title="Тайный ход", text="Я знаю про тоннель.", need_flags=["tunnel"], closed="mystery")
        Variant.objects.create(step=cls.first, title="Скрытый", text="x", need_flags=["never"], closed="hidden")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def box(self, profile=None):
        return Box.of_profile(profile or self.profile, user=self.ivan)

    def subjects(self, folder="inbox"):
        return [row.letter.subject for row in self.box().letters_in(folder)]

    def started(self):
        deliver_by_slug(self.ivan, "door", profile=self.profile)
        return TalkState.objects.get(user=self.ivan)

    def test_the_hook_starts_a_conversation_and_the_reply_offers_its_variants(self):
        self.started()
        self.assertEqual(self.subjects(), ["Код?"])
        _, offers = talk.offers_for_reply(self.ivan, self.profile, frozenset(), self.ask)
        self.assertEqual([(o.variant.title, o.open) for o in offers], [("Назвать код", True), ("Тайный ход", False)])   # скрытого нет

    def test_the_chosen_word_leads_its_own_way(self):
        self.started()
        sent = talk.send(self.box(), frozenset(), to="guard@port", subject="Re: Код?", typed="Код: 4471. Склад 7.", variant=self.code, reply_item=self.ask)
        self.assertEqual(sent.kind, "ok")
        self.assertEqual(TalkState.objects.get(user=self.ivan).step, self.done)
        self.assertEqual(set(self.subjects()), {"Код?", "Принято", "Склад 7"})
        self.assertFalse(Flag.objects.exists())                                           # у слова свой исход, без метки
        self.assertEqual(self.subjects("sent"), ["Re: Код?"])

    def test_wrong_answers_go_on_and_then_exhaust(self):
        self.started()
        first = talk.send(self.box(), frozenset(), to="guard@port", typed="Код: 1111. Склад 9.", variant=self.code, reply_item=self.ask)
        self.assertEqual((first.kind, first.left), ("wrong", 1))
        self.assertIn("Неверно", self.subjects())
        second = talk.send(self.box(), frozenset(), to="guard@port", typed="Код: 2222. Склад 9.", variant=self.code, reply_item=self.ask)
        self.assertEqual(second.kind, "exhausted")
        self.assertEqual(TalkState.objects.get(user=self.ivan).step, self.lost)
        self.assertIn("Хватит", self.subjects())
        self.assertEqual(talk.send(self.box(), frozenset(), to="guard@port", typed="Код: 4471. Склад 9.", variant=self.code).kind, "closed")

    def test_a_typed_text_that_differs_is_refused_without_an_attempt(self):
        self.started()
        self.assertEqual(talk.send(self.box(), frozenset(), to="guard@port", typed="привет", variant=self.code).kind, "mismatch")
        self.assertEqual(TalkState.objects.get(user=self.ivan).attempts, {})

    def test_a_new_letter_opens_a_conversation_an_unknown_address_bounces_and_an_account_receives(self):
        opening = Step.objects.create(conversation=self.talk, name="hello", order=0, opening=True)
        hello = Variant.objects.create(step=opening, title="Представиться", text="Я из порта.", outcomes={"ok": [{"do": "goto", "step": "ask"}]})
        persona, offers = talk.offers_for_address(self.ivan, self.profile, frozenset(), "GUARD@port")
        self.assertEqual((persona, [o.variant for o in offers]), (self.guard, [hello]))
        self.assertEqual(talk.send(self.box(), frozenset(), to="guard@port", typed="Я из порта.", variant=hello).kind, "ok")
        self.assertEqual(TalkState.objects.get(user=self.ivan).step, self.first)
        bounced = talk.send(self.box(), frozenset(), to="nobody@nowhere", subject="Эй", typed="кто тут?")
        self.assertEqual(bounced.kind, "bounced")
        returned = next(row for row in self.box().letters_in("inbox") if row.letter.sender.startswith("MAILER-DAEMON"))
        self.assertIn("<nobody@nowhere>: host or user unknown", returned.letter.body)
        talk.send(self.box(), frozenset(), to=self.captain.mail, subject="Себе", typed="заметка")
        self.assertEqual([r.letter.subject for r in self.box(self.captain).letters_in("inbox")], ["Себе"])

    def test_a_variant_for_another_account_and_a_proof_attachment(self):
        self.started()
        boss = Variant.objects.create(step=self.first, title="От капитана", text="Приказ.", account=self.captain,
                                      attachment={"signed": "seal"}, outcomes={"ok": [{"do": "goto", "step": "done"}]})
        _, mine = talk.offers_for_address(self.ivan, self.profile, frozenset(), "guard@port")
        self.assertFalse(next(o for o in mine if o.variant == boss).open)               # с учётки ivan закрыт
        seal = key_item("seal")
        order = Item.objects.create(slug="order", name="order.txt", body="приказ")
        ItemSignature.objects.create(item=order, key=seal, valid=True)
        make_file(self.main, "/home/captain/order.txt", body="приказ")
        as_captain = self.box(self.captain)
        TalkState.objects.filter(user=self.ivan).update(profile=self.captain)
        plain = as_captain.view.get("/home/ivan/report.txt")
        self.assertEqual(talk.send(as_captain, frozenset(), to="guard@port", typed="Приказ.", variant=boss, attachment=plain).kind, "wrong")
        as_captain.view.put_item("/home/captain/signed.txt", order)
        signed = as_captain.view.get("/home/captain/signed.txt")
        self.assertEqual(talk.send(as_captain, frozenset(), to="guard@port", typed="Приказ.", variant=boss, attachment=signed).kind, "ok")

    def test_forwarding_a_letter_and_rewards(self):
        self.started()
        key_item("dock")
        Variant.objects.create(step=self.first, title="Переслать приказ", mode="forward", forward_of=self.ask,
                               outcomes={"ok": [{"do": "key", "slug": "dock"}, {"do": "hook", "text": "alert intruder count=2\nopen apps/wiki/go/dock/"}]})
        _, offers = talk.offers_for_forward(self.ivan, self.profile, frozenset(), "guard@port", self.ask)
        sent = talk.send(self.box(), frozenset(), to="guard@port", variant=offers[0].variant, forward_item=self.ask)
        self.assertEqual(sent.kind, "ok")
        self.assertEqual([effect["op"] for effect in sent.effects], ["alert", "open"])
        from filesystem import keystore

        self.assertTrue(self.box().view.exists(f"{keystore.secrets_dir(self.main, 'ivan')}/dock"))


@override_settings(FORCE_SCRIPT_NAME=None)
class TalkAppTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="intercom", icon="mail", path="/apps/mail/")
        make_file(cls.main, "/home/ivan/report.txt", body="отчёт")
        cls.ivan = get_user_model().objects.create_user("ivan", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.main, user=cls.ivan, name="Ivan", login="ivan", freq=1)
        guard = Persona.objects.create(address="guard@port", name="Охрана")
        conversation = Conversation.objects.create(persona=guard, slug="door", title="Дверь")
        cls.ask = letter("guard-ask", "guard@port", "Код?", "Назовите код.")
        step = Step.objects.create(conversation=conversation, name="ask", letter=cls.ask)
        Step.objects.create(conversation=conversation, name="done", order=2, letter=letter("guard-ok", "guard@port", "Проходите"))
        cls.variant = Variant.objects.create(step=step, title="Код", text="Код {{4471}}", outcomes={"ok": [{"do": "goto", "step": "done"}]})

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.ivan)
        session = self.client.session
        session[SESSION_KEY] = Session.objects.create(user=self.ivan, profile=self.profile, seen_at=timezone.now()).pk
        session.save()
        deliver_by_slug(self.ivan, "door", profile=self.profile)

    def test_reply_options_hide_secrets_and_sending_moves_on(self):
        path = self.client.get("/apps/mail/api/messages/").json()["messages"][0]["id"]
        options = self.client.get("/apps/mail/api/compose/", {"reply": path}).json()
        self.assertEqual((options["to"], options["subject"]), ("guard@port", "Re: Код?"))
        self.assertEqual(options["offers"][0]["segments"], [{"text": "Код "}, {"hidden": 4}])
        self.assertNotIn("4471", json.dumps(options))
        answer = self.client.post("/apps/mail/api/send/", data=json.dumps({"to": "guard@port", "subject": options["subject"], "text": "Код 4471",
                                                                         "variant": options["offers"][0]["id"], "reply": path}), content_type="application/json")
        self.assertEqual(answer.json()["kind"], "ok")
        subjects = [m["subject"] for m in self.client.get("/apps/mail/api/messages/").json()["messages"]]
        self.assertIn("Проходите", subjects)
        self.assertIn("Re: Код?", subjects)

    def test_the_file_picker_lists_the_home_of_the_account(self):
        data = self.client.get("/apps/mail/api/files/").json()
        self.assertEqual(data["path"], "/home/ivan")
        self.assertEqual([row["name"] for row in data["entries"]], ["report.txt"])
