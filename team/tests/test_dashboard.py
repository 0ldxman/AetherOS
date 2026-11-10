"""Главная Студии: игроки в мире, замечания к миру, число изменений за сегодня.

Запуск: python manage.py test team
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from django.utils import timezone

from machines.models import Machine, MachineProfile, Session
from team.testing import full_role


@override_settings(FORCE_SCRIPT_NAME=None)
class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.anna = User.objects.create_user("anna", password="pw", is_staff=True, role=full_role())
        cls.player = User.objects.create_user("ivan", password="pw")
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        profile = MachineProfile.objects.create(machine=cls.machine, user=cls.player, name="Ivan", login="ivan", freq=1)
        Session.objects.create(user=cls.player, profile=profile, seen_at=timezone.now())
        MachineProfile.objects.create(machine=cls.machine, login="open", name="Open", freq=2)       # ни пароля, ни ключа

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.anna)

    def test_the_dashboard_shows_players_problems_and_todays_changes(self):
        data = self.client.get("/studio/api/dashboard").json()
        self.assertEqual([(p["player"], p["login"], p["hostname"]) for p in data["online"]], [("ivan", "ivan", "aether-main")])
        problem = next(p for p in data["problems"] if p["kind"] == "machine")
        self.assertIn("open", problem["text"])
        self.assertEqual(problem["link"], f"#/machines/{self.machine.pk}")
        self.assertEqual(data["changes_today"], 0)
        self.client.post("/studio/api/machines/randomart", data="{}", content_type="application/json")   # чтение не считается
        self.assertEqual(self.client.get("/studio/api/dashboard").json()["changes_today"], 0)

    def test_me_names_the_author_for_the_filter_of_own_changes(self):
        self.assertEqual(self.client.get("/studio/api/me").json()["id"], self.anna.pk)
