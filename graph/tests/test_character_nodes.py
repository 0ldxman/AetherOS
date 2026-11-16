"""Ноды персонажа: «Получил сообщение» → «Ответить» (с отметкой сценария у кукловода), «Написать» списку адресатов."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from characters.models import Character, Inbound, Reply
from engine.events import emit
from graph import runtime
from graph.tests.test_data import f
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile
from mail.models import Persona


class CharacterNodeTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        self.core = Machine.objects.create(name="Core", hostname="core")
        self.guard = MachineProfile.objects.create(machine=self.core, login="guard", name="guard", freq=1)
        self.zk = Character.objects.create(code="ZK3", name="Зоркий")
        Persona.objects.create(address="zk3@relay", character=self.zk)

    def test_a_scenario_answers_a_message_and_the_puppeteer_sees_who(self):
        make([node("w", "on:character.wrote", channel="mail", character="ZK3"), node("r", "act:character.reply", text="Принято, {player}.")],
             [wire("w", "sent", "r"), f("w", "message", "r", "message")], slug="zk-auto")
        inbound = Inbound.objects.create(character=self.zk, channel="mail", user=self.ivan, sender=self.guard.mail, subject="Помогите",
                                         text="есть кто?", ref={"persona": "zk3@relay"})
        emit("character.wrote", self.ivan, character="ZK3", channel="forum", text="мимо", message=inbound.pk)        # другой канал
        self.assertFalse(Reply.objects.exists())
        emit("character.wrote", self.ivan, character="ZK3", channel="mail", text="есть кто?", message=inbound.pk)
        reply = Reply.objects.get()
        self.assertEqual((reply.subject, reply.text, reply.graph, reply.status), ("Re: Помогите", "Принято, ivan.", "zk-auto", "sent"))
        inbound.refresh_from_db()
        self.assertEqual((inbound.status, inbound.graph), ("answered", "zk-auto"))

    def test_say_by_mail_to_a_list_of_an_account_and_a_player(self):
        graph = make([node("m", "manual"), node("s", "act:character.say", channel="mail", character="ZK3", to="list",
                                               targets=["guard@core", "ivan", "guard@core"], subject="Сводка", text="Всем постам.")],
                     [wire("m", "fire", "s")], slug="zk-say")
        runtime.start_manual(graph, "m", self.ivan)
        rows = Reply.objects.order_by("pk")
        self.assertEqual([(r.ref["profile"], r.status, r.graph) for r in rows],
                         [(self.guard.pk, "sent", "zk-say"), (MachineProfile.objects.get(machine=self.main, user=self.ivan).pk, "sent", "zk-say")])
        bad = make([node("m", "manual"), node("s", "act:character.say", channel="mail", character="ZK3", to="list", targets=["nobody"],
                                             subject="x", text="y")], [wire("m", "fire", "s")], slug="zk-bad")
        runtime.start_manual(bad, "m", self.ivan)
        self.assertEqual(Reply.objects.count(), 2)
