"""API машин в студии: список, обзор с предупреждениями, учётки и токены, проверка входа, журнал, разблокировка и выкидывание.

Запуск: python manage.py test studio.tests.test_machines
"""
import json
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from filesystem.testing import key_item
from machines.access import entry
from machines.models import EntryPolicy, LoginEvent, Machine, MachineProfile, Session

API = "/studio/api"


@override_settings(FORCE_SCRIPT_NAME=None)
class MachinesApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.boss = users.objects.create_user("boss", password="pw", is_staff=True)
        cls.ivan = users.objects.create_user("ivan", password="pw")
        cls.core = Machine.objects.create(name="Core", hostname="aether-core", status=Machine.Status.ONLINE)
        cls.policy = EntryPolicy.objects.create(name="strict", sources="gw-*", max_attempts=1, lock_seconds=600)
        cls.vault = MachineProfile.objects.create(
            machine=cls.core, login="vault", name="Vault", freq=14, password_hash=make_password("right"), entry_policy=cls.policy,
        )
        cls.open = MachineProfile.objects.create(machine=cls.core, login="guest", name="Guest", freq=14, groups=["ghosts"])
        key_item("cardkey")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def call(self, method, path, body=None):
        response = getattr(self.client, method)(API + path, data=json.dumps(body, default=str) if body is not None else None,
                                                 content_type="application/json")
        return response.status_code, (response.json() if response.content else None)

    def test_the_list_counts_accounts_players_online_and_refusals(self):
        Session.objects.create(user=self.ivan, profile=self.open, seen_at=timezone.now())
        Session.objects.create(user=self.boss, profile=self.open, seen_at=timezone.now() - timedelta(hours=1))
        LoginEvent.objects.create(profile=self.vault, user=self.ivan, kind="bad_password")
        LoginEvent.objects.create(profile=self.vault, user=self.ivan, kind="ok")
        row = self.call("get", "/machines")[1][0]
        self.assertEqual((row["hostname"], row["accounts"], row["online"], row["refusals"]), ("aether-core", 2, 1, 1))

    def test_the_overview_warns_about_open_accounts_and_unknown_groups(self):
        status, data = self.call("get", f"/machines/{self.core.pk}")
        self.assertEqual(status, 200)
        texts = " ".join(w["text"] for w in data["warnings"])
        self.assertIn("guest нет ни пароля, ни ключа", texts)
        self.assertIn("ghosts", texts)
        vault = next(a for a in data["accounts"] if a["login"] == "vault")
        self.assertEqual(vault["policy"], {"id": self.policy.pk, "name": "strict", "origin": "profile"})

    def test_an_account_is_created_with_a_password_and_a_key_expression(self):
        status, account = self.call("post", f"/machines/{self.core.pk}/accounts", {
            "login": "ops", "password": "s3cret", "keys": "cardkey and not alarm", "groups": ["users"],
        })
        self.assertEqual(status, 200, account)
        profile = MachineProfile.objects.get(pk=account["id"])
        self.assertTrue(check_password("s3cret", profile.password_hash))
        self.assertEqual(account["keys"], "cardkey and not alarm")
        self.assertEqual(profile.mail, "ops@aether-core")

        status, answer = self.call("put", f"/machines/{self.core.pk}/accounts/{profile.pk}", {"login": "ops", "keys": "cardkey and ("})
        self.assertEqual(status, 400)
        self.assertIn("keys", answer["fields"])
        status, cleared = self.call("put", f"/machines/{self.core.pk}/accounts/{profile.pk}", {"login": "ops", "clear_password": True})
        self.assertFalse(cleared["has_password"])

    def test_tokens_are_made_and_dropped(self):
        status, token = self.call("post", f"/machines/{self.core.pk}/accounts/{self.vault.pk}/tokens", {"max_usage": 2})
        self.assertEqual(status, 200)
        self.assertTrue(token["token"].startswith("tk-"))
        self.assertEqual(len(self.call("get", f"/machines/{self.core.pk}/accounts/{self.vault.pk}")[1]["tokens"]), 1)
        self.call("delete", f"/machines/{self.core.pk}/accounts/{self.vault.pk}/tokens/{token['id']}")
        self.assertEqual(self.call("get", f"/machines/{self.core.pk}/accounts/{self.vault.pk}")[1]["tokens"], [])

    def test_the_check_answers_step_by_step(self):
        body = {"account": self.vault.pk, "source": "aether-main"}
        verdict = self.call("post", f"/machines/{self.core.pk}/check", body)[1]
        self.assertEqual((verdict["admitted"], verdict["kind"]), (False, "source"))
        verdict = self.call("post", f"/machines/{self.core.pk}/check", {**body, "source": "gw-02", "password": "right"})[1]
        self.assertTrue(verdict["admitted"])
        self.assertFalse(LoginEvent.objects.exists())

    def test_the_journal_filters_and_the_author_unlocks_and_kicks(self):
        LoginEvent.objects.create(profile=self.vault, user=self.ivan, kind="bad_password", source="gw-02")
        LoginEvent.objects.create(profile=self.vault, user=self.ivan, kind="locked", source="gw-02")
        self.assertGreater(entry.locked_seconds(self.ivan, self.vault), 0)
        rows = self.call("get", f"/machines/{self.core.pk}/events?kind=locked")[1]
        self.assertEqual([r["kind"] for r in rows], ["locked"])

        self.assertEqual(self.call("post", f"/machines/{self.core.pk}/unlock", {"account": self.vault.pk, "player": "ivan"})[0], 200)
        self.assertEqual(entry.locked_seconds(self.ivan, self.vault), 0)
        Session.objects.create(user=self.ivan, profile=self.vault, seen_at=timezone.now())
        answer = self.call("post", f"/machines/{self.core.pk}/kick", {"account": self.vault.pk, "player": "ivan"})[1]
        self.assertEqual(answer["sessions"], 1)
        self.assertIsNotNone(Session.objects.get(user=self.ivan, profile=self.vault).kick_at)

    def test_the_header_is_edited_and_a_players_own_account_is_not_deleted(self):
        status, data = self.call("put", f"/machines/{self.core.pk}", {
            "hostname": "aether-core", "name": "Core II", "system": "AETHER", "status": "MAINTENANCE", "entry_policy": self.policy.pk,
        })
        self.assertEqual((status, data["name"], data["policy"]["name"]), (200, "Core II", "strict"))
        own = MachineProfile.objects.create(machine=self.core, user=self.ivan, login="ivan", name="Ivan", freq=1)
        self.assertEqual(self.call("delete", f"/machines/{self.core.pk}/accounts/{own.pk}")[0], 400)
        self.assertEqual(self.call("delete", f"/machines/{self.core.pk}/accounts/{self.open.pk}")[0], 200)

    def test_a_policy_comes_with_the_grid_of_its_windows(self):
        shift = EntryPolicy.objects.create(name="shift", windows="mon-fri: 9:00-13:00")
        data = self.call("get", f"/machines/policies/{shift.pk}")[1]
        self.assertEqual(data["sources"], [])
        monday, saturday = data["grid"][0], data["grid"][5]
        self.assertEqual([slot for slot, open_ in enumerate(monday) if open_], list(range(18, 26)))     # 9:00..13:00 по получасам
        self.assertFalse(any(saturday))
        self.assertIsNone(self.call("get", f"/machines/policies/{self.policy.pk}")[1]["grid"])
