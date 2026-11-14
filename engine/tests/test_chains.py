"""Цепочки: шаги-условия по порядку, отметки прохождения от событий игрока, воронка, кто первым, разрывы."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import chains
from engine.events import emit
from engine.models import Chain, ChainReach, ChainStep
from machines.models import Machine, MachineProfile
from mail.models import Flag
from team.testing import full_role


class ChainTests(TestCase):
    def setUp(self):
        User = get_user_model()
        machine = Machine.objects.create(name="Main", hostname="aether-main")
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")
        for user in (self.ivan, self.anna):
            MachineProfile.objects.create(machine=machine, user=user, name=user.username, login=user.username, freq=1)
        self.chain = Chain.objects.create(slug="door", title="Door")
        self.one = ChainStep.objects.create(chain=self.chain, order=0, title="Met the guard", condition="flag:met")
        self.two = ChainStep.objects.create(chain=self.chain, order=1, title="Saw the door", condition="flag:door")

    def test_steps_are_reached_in_order_on_player_events(self):
        Flag.objects.create(user=self.ivan, name="door")
        emit("file.read", self.ivan, path="/x")
        self.assertFalse(ChainReach.objects.exists())                 # второй шаг без первого не считается
        Flag.objects.create(user=self.ivan, name="met")
        emit("file.read", self.ivan, path="/x")
        self.assertEqual(ChainReach.objects.filter(user=self.ivan).count(), 2)

    def test_report_shows_the_funnel_first_and_who_waits(self):
        Flag.objects.create(user=self.anna, name="met")
        chains.update(self.anna)
        Flag.objects.create(user=self.ivan, name="met")
        Flag.objects.create(user=self.ivan, name="door")
        chains.update(self.ivan)
        report = chains.report(self.chain)
        first, second = report["steps"]
        self.assertEqual((report["players"], first["reached"], first["first"][0], second["reached"]), (2, 2, self.anna, 1))
        self.assertEqual([w["user"] for w in second["waiting"]], [self.anna])
        self.assertEqual(report["finished"], [self.ivan])
        self.assertEqual(second["breaks"], ["flag:door"])               # flag:door никто не ставит

    def test_studio_edits_steps_and_keeps_reaches(self):
        boss = get_user_model().objects.create_user("boss", is_staff=True, role=full_role())
        self.client.force_login(boss)
        Flag.objects.create(user=self.ivan, name="met")
        chains.update(self.ivan)
        body = {"slug": "door", "title": "Door", "steps": [{"id": self.one.pk, "title": "Met", "condition_text": "flag:met"},
                                                           {"title": "Got key", "condition_text": "mask"}]}
        response = self.client.put(f"/studio/api/world/chains/{self.chain.pk}", body, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(([s["title"] for s in data["steps"]], data["funnel"][0]["reached"], data["funnel"][0]["first_player"]), (["Met", "Got key"], 1, "ivan"))
        bad = {**body, "steps": [{"title": "x", "condition_text": ""}]}
        self.assertEqual(self.client.put(f"/studio/api/world/chains/{self.chain.pk}", bad, content_type="application/json").status_code, 400)
