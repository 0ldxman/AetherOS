"""Учётки и игроки: кому принадлежит учётка, кто работает под ней, привязка и отвязка.

Запуск: python manage.py test studio.tests.test_accounts_players
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from machines.models import LoginEvent, Machine, MachineProfile, Session


@override_settings(FORCE_SCRIPT_NAME=None)
class AccountPlayersTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        User = get_user_model()
        self.boss = User.objects.create_user("boss", password="pw", is_staff=True)
        self.ivan = User.objects.create_user("ivan", password="pw")
        self.petr = User.objects.create_user("petr", password="pw")
        self.client.force_login(self.boss)
        self.core = Machine.objects.create(name="Core", hostname="core")
        self.vault = MachineProfile.objects.create(machine=self.core, name="vault", login="vault", freq=14.23)
        self.home = MachineProfile.objects.create(machine=self.core, name="ivan", login="ivan", freq=0, user=self.ivan)

    def call(self, method, path, body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"/studio/api/machines/{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def test_players_are_found_by_a_part_of_the_login(self):
        self.assertEqual(self.call("get", "players?q=iv")[1], ["ivan"])
        self.assertEqual(self.call("get", "players")[1], ["boss", "ivan", "petr"])

    def test_an_account_can_be_made_for_a_player_once_per_machine(self):
        status, made = self.call("post", f"{self.core.pk}/accounts", {"login": "reader", "player": "petr"})
        self.assertEqual((status, made["owner"]), (200, "petr"))
        status, error = self.call("post", f"{self.core.pk}/accounts", {"login": "reader2", "player": "petr"})
        self.assertEqual(status, 400)
        self.assertFalse(MachineProfile.objects.filter(login="reader2").exists())          # отказ не оставляет учётку
        self.assertEqual(self.call("post", f"{self.core.pk}/accounts", {"login": "x", "player": "nobody"})[0], 400)

    def test_binding_and_unbinding_an_existing_account(self):
        status, bound = self.call("post", f"{self.core.pk}/accounts/{self.vault.pk}/bind", {"player": "petr"})
        self.assertEqual((status, bound["owner"]), (200, "petr"))
        self.assertEqual(self.call("post", f"{self.core.pk}/accounts/{self.vault.pk}/bind", {"player": "ivan"})[0], 400)   # у ivan уже своя
        status, free = self.call("post", f"{self.core.pk}/accounts/{self.vault.pk}/bind", {"player": None})
        self.assertEqual((status, free["owner"]), (200, None))

    def test_who_works_under_an_account(self):
        Session.objects.create(user=self.ivan, profile=self.vault, seen_at=timezone.now())
        LoginEvent.objects.create(profile=self.vault, user=self.ivan, kind="ok")
        LoginEvent.objects.create(profile=self.vault, user=self.petr, kind="bad_password")
        rows = {r["player"]: r for r in self.call("get", f"{self.core.pk}/accounts/{self.vault.pk}/players")[1]}
        self.assertEqual((rows["ivan"]["online"], rows["ivan"]["last_login"] is not None, rows["ivan"]["refusals"]), (True, True, 0))
        self.assertEqual((rows["petr"]["online"], rows["petr"]["refusals"]), (False, 1))

    def test_nobody_yet_means_an_empty_list(self):
        self.assertEqual(self.call("get", f"{self.core.pk}/accounts/{self.vault.pk}/players")[1], [])
