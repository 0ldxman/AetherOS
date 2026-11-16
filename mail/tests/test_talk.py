"""Переписка с персонажами на возможностях сценария: набор с секретами и развилками, лимит попыток счётчиком, новое письмо
и возврат от MAILER-DAEMON, письмо с чужой учётки, вложение-доказательство, пересылка, условие доступа, приложение почты.

Запуск: python manage.py test mail
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from engine import values as store
from filesystem.models import Item, ItemSignature
from filesystem.testing import key_item, make_app, make_file
from graph import runtime
from graph.models import Graph
from machines.current import SESSION_KEY
from machines.models import Machine, MachineProfile, Session
from mail import talk
from mail.boxes import Box
from mail.models import Persona


class CheckTests(TestCase):
    def test_secret_choice_case_and_yo(self):
        template = "Код двери: {{4471}}. Груз на [[склад: складе 7|складе 9]]. Всё."
        self.assertEqual(talk.check(template, "код двери: 4471. груз на складе 9. всё.").verdict, "ok")
        self.assertEqual(talk.check(template, "Код двери: 4471. Груз на складе 9. Всё.").words, ["складе 9"])
        self.assertEqual(talk.check(template, "Код двери: 1111. Груз на складе 7. Всё.").verdict, "wrong")
        self.assertEqual(talk.check(template, "Код двери: 4471. Груз на складе 8. Всё.").verdict, "mismatch")
        self.assertEqual(talk.check("Ещё {{ёж}}", "еще  ЕЖ").verdict, "ok")
        self.assertEqual(talk.public("Код {{4471}} [[a|b]]"), [{"text": "Код "}, {"hidden": 4}, {"text": " "}, {"choices": ["a", "b"]}])


def letter(slug, sender, subject, body=""):
    return Item.objects.create(slug=slug, name=slug, format="msg", body=f"From: {sender}\nTo: {{to}}\nSubject: {subject}\n\n{body}")


def node(node_id, kind, **data):
    return {"id": node_id, "type": kind, "x": 0, "y": 0, "data": data}


def wire(src, out, dst, inp="in"):
    return {"from": src, "out": out, "to": dst, "in": inp}


def offered(node_id, opened=None, **data):
    """Сущность «Возможность» node_id и «Открыть» её (нода o<node_id>, opened — её поля)."""
    return [node(node_id, "ent:offer", **data), node("o" + node_id, "act:offer", offer=f"door:{node_id}", **(opened or {}))]


def door(extra_nodes=(), extra_wires=()):
    """Персонаж спрашивает код; варианты ответа — возможности группы «ask»; исходы — письма. Слово развилки «склад» ведёт
    своей дорогой; две неверные попытки (счётчик игрока) закрывают вариант."""
    nodes = [node("m", "manual"), node("ask", "act:mail", variant="player", item="guard-ask"),
             *offered("code", mode="reply", to="guard@port", letter="guard-ask", title="Назвать код", text="Код: {{4471}}. Склад [[склад: 7|9]].",
                      group="ask"),
             *offered("tunnel", mode="reply", to="guard@port", title="Тайный ход", text="Я знаю про тоннель.", group="ask"),
             *offered("hidden", mode="reply", to="guard@port", title="Скрытый", text="x", group="ask"),
             node("knows", "fact", expr="tag:tunnel"), node("never", "fact", expr="tag:never"), node("yes", "boolean", value=True),
             node("qtunnel", "act:offer", state="mystery", offer="door:tunnel"),
             node("u", "on:offer.used", offer="door:code", repeat="always"), node("seven", "compare", op="eq", b="7"), node("which", "check"),
             node("m7", "act:mail", variant="player", item="guard-7"), node("m9", "act:mail", variant="player", item="guard-thanks"),
             node("tries", "act:count", variant="add", owner="player", name="tries", delta=1), node("limit", "check", condition="count:tries>=2"),
             node("shut", "act:offer", state="hidden", offer="door:code"), node("angry", "act:mail", variant="player", item="guard-angry"),
             node("warn", "act:mail", variant="player", item="guard-warn"), *extra_nodes]
    wires = [wire("m", "fire", "ask"), wire("ask", "next", "ocode"), wire("knows", "value", "otunnel"), wire("never", "value", "ohidden"), wire("yes", "value", "qtunnel"),
             wire("u", "ok", "which"), wire("u", "fork:склад", "seven", "f:a"), wire("seven", "value", "which", "f:condition"),
             wire("which", "yes", "m7"), wire("which", "no", "m9"),
             wire("u", "wrong", "tries"), wire("tries", "next", "limit"), wire("limit", "yes", "shut"), wire("shut", "next", "angry"), wire("limit", "no", "warn"),
             *extra_wires]
    graph = Graph.objects.create(slug="door", title="Дверь", active=True, doc={"nodes": nodes, "wires": wires})
    runtime.rebuild_starts(graph)
    return graph


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
        cls.ask = letter("guard-ask", "guard@port", "Код?", "Назовите код двери.")
        letter("guard-thanks", "guard@port", "Принято", "Проходите.")
        letter("guard-warn", "guard@port", "Неверно", "Это не тот код.")
        letter("guard-angry", "guard@port", "Хватит", "Я вызываю патруль.")
        letter("guard-7", "guard@port", "Склад 7", "Седьмой открыт.")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def box(self, profile=None):
        return Box.of_profile(profile or self.profile, user=self.ivan)

    def subjects(self, folder="inbox"):
        return [row.letter.subject for row in self.box().letters_in(folder)]

    def started(self, graph=None):
        graph = graph or door()
        runtime.start(graph, "m", "fire", self.ivan, {"host": "aether-main", "login": "ivan"}, repeat="always")
        return graph

    def send(self, typed, offer="door:code", box=None, **kw):
        return talk.send(box or self.box(), to="guard@port", subject="Re: Код?", typed=typed, offer=offer, reply_item=kw.pop("reply_item", self.ask), **kw)

    def test_a_letter_outside_offers_waits_in_the_character_inbox(self):
        from characters.models import Character, Inbound

        face = Character.objects.create(code="GRD", name="Port guard")
        Persona.objects.filter(pk=self.guard.pk).update(character=face)
        sent = talk.send(self.box(), to="guard@port", subject="Hello", typed="Is anyone at the gate?")
        row = Inbound.objects.get()
        self.assertEqual((row.character, row.channel, row.subject, row.text, row.ref["path"]), (face, "mail", "Hello", "Is anyone at the gate?", sent.path))
        self.assertEqual(self.subjects(), [])                          # игроку тишина: ни ответа, ни отказа

    def test_the_scenario_writes_and_the_reply_offers_its_variants(self):
        self.started()
        self.assertEqual(self.subjects(), ["Код?"])
        offers = talk.offers_to_answer(self.box(), "guard@port", reply_item=self.ask)
        self.assertEqual([(o.spec["title"], o.open) for o in offers], [("Назвать код", True), ("Тайный ход", False)])   # скрытого нет
        store.set_tag("player", self.ivan.pk, "tunnel")
        offers = talk.offers_to_answer(self.box(), "guard@port", reply_item=self.ask)
        self.assertTrue(next(o for o in offers if o.spec["title"] == "Тайный ход").open)

    def test_the_chosen_word_leads_its_own_way_and_closes_the_group(self):
        self.started()
        sent = self.send("Код: 4471. Склад 7.")
        self.assertEqual(sent.kind, "ok")
        self.assertEqual(set(self.subjects()), {"Код?", "Склад 7"})                     # исход слова 9 не сработал
        self.assertEqual(self.subjects("sent"), ["Re: Код?"])
        self.assertEqual(talk.offers_to_answer(self.box(), "guard@port", reply_item=self.ask), [])         # группа закрыта
        self.assertEqual(self.send("Код: 4471. Склад 7.").kind, "closed")

    def test_wrong_answers_count_and_the_scenario_closes_the_variant(self):
        self.started()
        first = self.send("Код: 1111. Склад 9.")
        self.assertEqual(first.kind, "wrong")
        self.assertIn("Неверно", self.subjects())
        self.assertEqual(self.send("Код: 2222. Склад 9.").kind, "wrong")
        self.assertIn("Хватит", self.subjects())
        self.assertEqual(self.send("Код: 4471. Склад 9.").kind, "closed")

    def test_a_typed_text_that_differs_is_refused_without_an_attempt(self):
        self.started()
        self.assertEqual(self.send("привет").kind, "mismatch")
        self.assertEqual(self.send("Код: 1111. Склад 9.").kind, "wrong")
        self.assertEqual(store.get("count", "player", self.ivan.pk, "tries"), 1)

    def test_a_new_letter_by_condition_an_unknown_address_bounces_and_an_account_receives(self):
        graph = door([node("always", "boolean", value=True),
                      *offered("hello", mode="new", to="guard@port", title="Представиться", text="Я из порта.")],
                     [wire("always", "value", "ohello")])
        offers = talk.offers_to_answer(self.box(), "GUARD@port")
        self.assertEqual([o.key for o in offers], ["door:hello"])
        self.assertEqual(talk.send(self.box(), to="guard@port", typed="Я из порта.", offer="door:hello").kind, "ok")
        self.assertEqual(talk.offers_to_answer(self.box(), "guard@port"), [])          # использована — закрыта для ivan
        self.assertTrue(graph.offers.filter(standing=True).exists())
        bounced = talk.send(self.box(), to="nobody@nowhere", subject="Эй", typed="кто тут?")
        self.assertEqual(bounced.kind, "bounced")
        returned = next(row for row in self.box().letters_in("inbox") if row.letter.sender.startswith("MAILER-DAEMON"))
        self.assertIn("<nobody@nowhere>: host or user unknown", returned.letter.body)
        talk.send(self.box(), to=self.captain.mail, subject="Себе", typed="заметка")
        self.assertEqual([r.letter.subject for r in self.box(self.captain).letters_in("inbox")], ["Себе"])

    def test_a_variant_for_another_account_and_an_attachment(self):
        graph = self.started(door([*offered("boss", mode="new", to="guard@port", title="От капитана", text="Приказ.", attach="order"),
                                   node("cur", "session.find"), node("sess", "ent:session"), node("cap", "compare", op="eq", b="captain@aether-main"),
                                   node("qboss", "act:offer", state="mystery", offer="door:boss")],
                                  [wire("cur", "value", "sess", "f:session"), wire("sess", "account", "cap", "f:a"), wire("cap", "value", "oboss"),
                                   wire("yes", "value", "qboss")]))
        mine = talk.offers_to_answer(self.box(), "guard@port")
        self.assertFalse(next(o for o in mine if o.key == "door:boss").open)                # с учётки ivan закрыт
        seal = key_item("seal")
        order = Item.objects.create(slug="order", name="order.txt", body="приказ")
        ItemSignature.objects.create(item=order, key=seal, valid=True)
        make_file(self.main, "/home/captain/order.txt", body="приказ")
        as_captain = self.box(self.captain)
        plain = as_captain.view.get("/home/ivan/report.txt")
        self.assertEqual(talk.send(as_captain, to="guard@port", typed="Приказ.", offer="door:boss", attachment=plain).kind, "wrong")
        as_captain.view.put_item("/home/captain/signed.txt", order)
        signed = as_captain.view.get("/home/captain/signed.txt")
        self.assertEqual(talk.send(as_captain, to="guard@port", typed="Приказ.", offer="door:boss", attachment=signed).kind, "ok")
        from engine.models import Event

        self.assertEqual(Event.objects.filter(name="offer.used").order_by("pk").last().data["attachment"], "ivan@aether-main:/home/captain/signed.txt")
        self.assertTrue(graph)

    def test_to_takes_a_character_and_reply_to_a_letter_of_the_sender_node(self):
        from characters.models import Character

        face = Character.objects.create(code="GRD", name="Port guard")
        Persona.objects.filter(pk=self.guard.pk).update(character=face)
        graph = self.started(door([node("face", "ent:character", character="GRD"), node("chat", "ent:offer", mode="reply", title="Привет", text="Привет."),
                                   node("ochat", "act:offer")],
                                  [wire("face", "value", "chat", "f:to"), wire("ask", "item", "chat", "f:letter"), wire("chat", "offer", "ochat", "f:offer"),
                                   wire("ocode", "next", "ochat")]))
        offers = talk.offers_to_answer(self.box(), "guard@port", reply_item=self.ask)
        self.assertIn("door:chat", [o.key for o in offers])
        other = letter("guard-other", "guard@port", "Другое")
        self.assertNotIn("door:chat", [o.key for o in talk.offers_to_answer(self.box(), "guard@port", reply_item=other)])
        self.assertTrue(graph)

    def test_the_attachment_can_be_this_very_file(self):
        self.started(door(offered("proof", mode="new", to="guard@port", title="Отчёт", text="Отчёт.", attach="ivan@aether-main:/home/ivan/report.txt"),
                          [wire("ocode", "next", "oproof")]))
        report = self.box().view.get("/home/ivan/report.txt")
        self.box().view.put_item("/home/ivan/copy.txt", report.item)
        copy = self.box().view.get("/home/ivan/copy.txt")
        self.assertEqual(talk.send(self.box(), to="guard@port", typed="Отчёт.", offer="door:proof", attachment=copy).kind, "wrong")
        self.assertEqual(talk.send(self.box(), to="guard@port", typed="Отчёт.", offer="door:proof", attachment=report).kind, "ok")

    def test_forwarding_a_letter(self):
        self.started(door(offered("fwd", mode="forward", to="guard@port", letter="guard-ask", title="Переслать"),
                          [wire("ocode", "next", "ofwd")]))
        self.assertEqual(talk.offers_to_answer(self.box(), "guard@port"), [o for o in talk.offers_to_answer(self.box(), "guard@port") if o.key != "door:fwd"])
        offers = talk.offers_to_answer(self.box(), "guard@port", forward_item=self.ask)
        self.assertEqual([o.key for o in offers], ["door:fwd"])
        sent = talk.send(self.box(), to="guard@port", offer="door:fwd", forward_item=self.ask)
        self.assertEqual(sent.kind, "ok")
        letter_row = next(row for row in self.box().letters_in("sent"))
        self.assertIn("Forwarded message", letter_row.letter.body)

    def test_the_used_event_gives_the_fork_and_the_letter(self):
        from engine.models import Event

        self.started()
        self.send("Код: 4471. Склад 9.")
        event = Event.objects.get(name="offer.used")
        self.assertEqual((event.data["offer"], event.data["result"], event.data["forks"], event.data["group"]), ("door:code", "ok", {"склад": "9"}, "ask"))
        self.assertTrue(event.data["placement"].startswith("ivan@aether-main:"))
        self.assertIn("Принято", self.subjects())


@override_settings(FORCE_SCRIPT_NAME=None)
class TalkAppTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="intercom", icon="mail", path="/apps/mail/")
        make_file(cls.main, "/home/ivan/report.txt", body="отчёт")
        cls.ivan = get_user_model().objects.create_user("ivan", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.main, user=cls.ivan, name="Ivan", login="ivan", freq=1)
        Persona.objects.create(address="guard@port", name="Охрана")
        cls.ask = letter("guard-ask", "guard@port", "Код?", "Назовите код.")
        letter("guard-ok", "guard@port", "Проходите")
        nodes = [node("m", "manual"), node("ask", "act:mail", variant="player", item="guard-ask"),
                 *offered("code", mode="reply", to="guard@port", title="Код", text="Код {{4471}}"),
                 node("u", "on:offer.used", offer="door:code", repeat="always"), node("ok", "act:mail", variant="player", item="guard-ok")]
        cls.graph = Graph.objects.create(slug="door", title="Дверь", active=True, doc={"nodes": nodes, "wires": [
            wire("m", "fire", "ask"), wire("ask", "next", "ocode"), wire("u", "ok", "ok")]})
        runtime.rebuild_starts(cls.graph)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.ivan)
        session = self.client.session
        session[SESSION_KEY] = Session.objects.create(user=self.ivan, profile=self.profile, seen_at=timezone.now()).pk
        session.save()
        runtime.start(self.graph, "m", "fire", self.ivan, {"host": "aether-main", "login": "ivan"}, repeat="always")

    def test_reply_options_hide_secrets_and_sending_moves_on(self):
        path = self.client.get("/apps/mail/api/messages/").json()["messages"][0]["id"]
        options = self.client.get("/apps/mail/api/compose/", {"reply": path}).json()
        self.assertEqual((options["to"], options["subject"]), ("guard@port", "Re: Код?"))
        self.assertEqual(options["offers"][0]["segments"], [{"text": "Код "}, {"hidden": 4}])
        self.assertNotIn("4471", json.dumps(options))
        answer = self.client.post("/apps/mail/api/send/", data=json.dumps({"to": "guard@port", "subject": options["subject"], "text": "Код 4471",
                                                                         "offer": options["offers"][0]["id"], "reply": path}), content_type="application/json")
        self.assertEqual(answer.json()["kind"], "ok")
        subjects = [m["subject"] for m in self.client.get("/apps/mail/api/messages/").json()["messages"]]
        self.assertIn("Проходите", subjects)
        self.assertIn("Re: Код?", subjects)

    def test_the_file_picker_lists_the_home_of_the_account(self):
        data = self.client.get("/apps/mail/api/files/").json()
        self.assertEqual(data["path"], "/home/ivan")
        self.assertEqual([row["name"] for row in data["entries"]], ["report.txt"])
