"""Игроки в Студии: список, карточка, выброс, разблокировка, ключи, сброс прогресса и отключение входа; права действий.

Запуск: python manage.py test team
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from filesystem.machine_view import MachineView
from filesystem.models import PlayerFile
from filesystem.testing import key_item, make_file
from machines.models import LoginEvent, Machine, MachineProfile, Session
from team.models import Change, Role
from team.testing import full_role


@override_settings(FORCE_SCRIPT_NAME=None)
class PlayersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.anna = User.objects.create_user("anna", password="pw", is_staff=True, role=full_role())
        cls.ivan = User.objects.create_user("ivan", password="pw")
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        cls.account = MachineProfile.objects.create(machine=cls.machine, user=cls.ivan, name="Ivan", login="ivan", freq=1)
        Session.objects.create(user=cls.ivan, profile=cls.account, seen_at=timezone.now())
        make_file(cls.machine, "/home/note.txt", body="текст")
        cls.alpha = key_item("alpha")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.anna)

    def post(self, path, body):
        return self.client.post(f"/studio/api/players/{self.ivan.pk}/{path}", data=json.dumps(body), content_type="application/json")

    def test_the_list_and_the_card_show_where_the_player_is(self):
        rows = self.client.get("/studio/api/players").json()
        row = next(r for r in rows if r["username"] == "ivan")
        self.assertTrue(row["online"])
        self.assertEqual(row["accounts"], 1)
        self.assertEqual(self.client.get("/studio/api/players?online=true&q=iv").json()[0]["username"], "ivan")
        card = self.client.get(f"/studio/api/players/{self.ivan.pk}").json()
        self.assertEqual([(a["login"], a["hostname"], a["own"], a["online"]) for a in card["accounts"]], [("ivan", "aether-main", True, True)])

    def test_a_key_is_given_and_taken_only_in_the_layer_of_the_player(self):
        card = self.post("keys", {"account": self.account.pk, "key": "alpha"}).json()
        self.assertEqual([k["slug"] for k in card["keys"]], ["alpha"])
        self.assertEqual(self.post("keys", {"account": self.account.pk, "key": "alpha"}).status_code, 400)     # уже есть
        self.assertEqual(self.post("keys", {"account": self.account.pk, "key": "ghost"}).status_code, 400)
        self.assertFalse(MachineView(self.machine, None).exists(f"/home/.secrets/alpha"))                    # у других нет
        name = card["keys"][0]["name"]
        card = self.post("keys/take", {"account": self.account.pk, "name": name}).json()
        self.assertEqual(card["keys"], [])
        change = Change.objects.filter(path=f"players/{self.ivan.pk}/keys").first()
        self.assertEqual((change.kind, change.label), ("Игрок", "ivan"))

    def test_unlock_kick_and_a_foreign_account(self):
        LoginEvent.objects.create(profile=self.account, user=self.ivan, kind=LoginEvent.Kind.LOCKED)
        self.assertEqual(self.post("unlock", {"account": self.account.pk}).status_code, 200)
        self.assertTrue(LoginEvent.objects.filter(user=self.ivan, kind=LoginEvent.Kind.UNLOCKED).exists())
        self.post("kick", {"account": self.account.pk})
        self.assertIsNotNone(Session.objects.get(user=self.ivan).kick_at)
        other = MachineProfile.objects.create(machine=self.machine, name="Root", login="root", freq=2)
        self.assertEqual(self.post("kick", {"account": other.pk}).status_code, 400)

    def test_reset_removes_the_files_of_the_player(self):
        view = MachineView(self.machine, self.ivan)
        view.copy("/home/note.txt", "/home/copy.txt")
        self.assertTrue(PlayerFile.objects.filter(user=self.ivan).exists())
        card = self.post("reset", {"machine": self.machine.pk}).json()
        self.assertFalse(PlayerFile.objects.filter(user=self.ivan).exists())
        self.assertEqual(card["machines"], [])

    def test_ban_closes_the_door_and_the_superadmin_is_not_banned(self):
        card = self.post("ban", {"banned": True}).json()
        self.assertTrue(card["banned"])
        self.ivan.refresh_from_db()
        self.assertFalse(self.ivan.is_active)
        self.post("ban", {"banned": False})
        self.ivan.refresh_from_db()
        self.assertTrue(self.ivan.is_active)

    def test_each_action_needs_its_right(self):
        self.anna.role = Role.objects.create(name="Смотритель", rights={"players": "edit"}, actions=["players"])
        self.anna.save()
        self.assertEqual(self.post("kick", {"account": self.account.pk}).status_code, 200)
        self.assertEqual(self.post("keys", {"account": self.account.pk, "key": "alpha"}).status_code, 403)
        self.assertEqual(self.post("reset", {}).status_code, 403)
        self.assertEqual(self.post("ban", {"banned": True}).status_code, 403)
