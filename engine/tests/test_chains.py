"""Цепочки: шаги-условия по порядку, отметки прохождения от событий игрока, воронка, кто первым, разрывы."""
from engine import values as store
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import chains
from engine.events import emit
from engine.models import Chain, ChainReach, ChainStep
from machines.models import Machine, MachineProfile


class ChainTests(TestCase):
    def setUp(self):
        User = get_user_model()
        machine = Machine.objects.create(name="Main", hostname="aether-main")
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")
        for user in (self.ivan, self.anna):
            MachineProfile.objects.create(machine=machine, user=user, name=user.username, login=user.username, freq=1)
        self.chain = Chain.objects.create(slug="door", title="Door")
        self.one = ChainStep.objects.create(chain=self.chain, order=0, title="Met the guard", condition="tag:met")
        self.two = ChainStep.objects.create(chain=self.chain, order=1, title="Saw the door", condition="tag:door")

    def test_steps_are_reached_in_order_on_player_events(self):
        store.set_tag("player", self.ivan.pk, "door")
        emit("file.read", self.ivan, path="/x")
        self.assertFalse(ChainReach.objects.exists())                 # второй шаг без первого не считается
        store.set_tag("player", self.ivan.pk, "met")
        emit("file.read", self.ivan, path="/x")
        self.assertEqual(ChainReach.objects.filter(user=self.ivan).count(), 2)

    def test_report_shows_the_funnel_first_and_who_waits(self):
        store.set_tag("player", self.anna.pk, "met")
        chains.update(self.anna)
        store.set_tag("player", self.ivan.pk, "met")
        store.set_tag("player", self.ivan.pk, "door")
        chains.update(self.ivan)
        report = chains.report(self.chain)
        first, second = report["steps"]
        self.assertEqual((report["players"], first["reached"], first["first"][0], second["reached"]), (2, 2, self.anna, 1))
        self.assertEqual([w["user"] for w in second["waiting"]], [self.anna])
        self.assertEqual(report["finished"], [self.ivan])
        self.assertEqual(second["breaks"], ["tag:door"])               # tag:door никто не ставит
