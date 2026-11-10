"""Права авторов: правило для каждого пути API Студии, уровни роли, действия, суперадмин и экран команды.

Запуск: python manage.py test team
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from team import members, rights
from team.models import Role


class RuleTests(TestCase):
    def test_every_path_of_the_studio_api_has_a_rule(self):
        from studio.api import api

        missing = []
        for prefix, router in api._routers:
            for path, view in router.path_operations.items():
                full = (prefix.strip("/") + "/" + path.strip("/")).strip("/")
                sample = full.replace("{int:", "{").replace("{", "").replace("}", "")
                for operation in view.operations:
                    for method in operation.methods:
                        if rights.rule_for(sample, method) is None:
                            missing.append(f"{method} {full}")
        self.assertEqual(missing, [])

    def test_reading_previews_editing_and_actions(self):
        self.assertEqual(rights.rule_for("machines/3", "GET"), rights.Rule("machines", rights.READ))
        self.assertEqual(rights.rule_for("items/1/protection/preview", "POST"), rights.Rule("items", rights.READ))
        self.assertEqual(rights.rule_for("machines/3", "PUT"), rights.Rule("machines", rights.EDIT))
        self.assertEqual(rights.rule_for("machines/3/kick", "POST"), rights.Rule("machines", rights.EDIT, "players"))
        self.assertEqual(rights.rule_for("machines/3/accounts/4/tokens/5", "DELETE"), rights.Rule("machines", rights.EDIT, "players"))
        self.assertEqual(rights.rule_for("items/1", "DELETE"), rights.Rule("items", rights.EDIT, "delete"))
        self.assertEqual(rights.rule_for("items/1/lock", "DELETE"), rights.Rule("items", rights.EDIT))       # снять свою метку не удаление
        self.assertEqual(rights.rule_for("file-formats/txt", "PUT").section, "formats")
        self.assertIsNone(rights.rule_for("unknown/1", "GET"))


@override_settings(FORCE_SCRIPT_NAME=None)
class StudioRightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.boss = User.objects.create_user("boss", password="pw", is_staff=True, is_superuser=True)
        cls.writer = Role.objects.create(name="Писатель", rights={"items": "edit", "machines": "read"}, actions=[])
        cls.anna = User.objects.create_user("anna", password="pw", is_staff=True, role=cls.writer)
        cls.loose = User.objects.create_user("loose", password="pw", is_staff=True)            # автор без роли
        cls.player = User.objects.create_user("player", password="pw")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def as_(self, user):
        self.client.force_login(user)

    def send(self, method, path, body=None):
        return getattr(self.client, method)(f"/studio/api/{path}", data=json.dumps(body or {}), content_type="application/json")

    def test_the_role_sets_the_level_of_each_section(self):
        self.as_(self.anna)
        self.assertEqual(self.client.get("/studio/api/machines").status_code, 200)
        refused = self.send("put", "machines/1", {"name": "x"})
        self.assertEqual(refused.status_code, 403)
        self.assertIn("Машины", refused.json()["detail"])
        self.assertEqual(self.client.get("/studio/api/systems").status_code, 403)                  # раздела нет в роли
        self.assertNotEqual(self.send("post", "items", {"name": "x"}).status_code, 403)

    def test_a_dangerous_action_needs_its_flag(self):
        self.anna.role = Role.objects.create(name="Машинист", rights={"machines": "edit", "items": "edit"})
        self.anna.save()
        self.as_(self.anna)
        refused = self.send("post", "machines/1/kick", {"player": 1})
        self.assertEqual(refused.status_code, 403)
        self.assertIn("выбрасывать", refused.json()["detail"])
        self.assertEqual(self.send("delete", "items/999").status_code, 403)                       # удаление без флага

    def test_an_author_without_a_role_only_looks(self):
        self.as_(self.loose)
        self.assertEqual(self.client.get("/studio/api/systems").status_code, 200)
        self.assertEqual(self.send("post", "items", {"name": "x"}).status_code, 403)

    def test_players_do_not_enter_the_studio_and_the_superadmin_can_do_everything(self):
        self.as_(self.player)
        self.assertEqual(self.client.get("/studio/api/me").status_code, 401)
        self.as_(self.boss)
        me = self.client.get("/studio/api/me").json()
        self.assertTrue(me["superuser"])
        self.assertEqual(set(me["rights"]["sections"].values()), {"edit"})
        self.assertEqual(me["rights"]["team"], "edit")

    def test_me_tells_the_interface_the_rights_of_the_author(self):
        self.as_(self.anna)
        me = self.client.get("/studio/api/me").json()["rights"]
        self.assertEqual(me["sections"]["items"], "edit")
        self.assertEqual(me["sections"]["machines"], "read")
        self.assertEqual(me["sections"]["systems"], "none")
        self.assertEqual(me["actions"], [])
        self.assertEqual(me["team"], "read")

    def test_only_the_superadmin_manages_the_team(self):
        self.as_(self.anna)
        self.assertEqual(self.client.get("/studio/api/team").status_code, 200)
        self.assertEqual(self.send("post", "team/roles", {"name": "Новая"}).status_code, 403)
        self.as_(self.boss)
        made = self.send("post", "team/roles", {"name": "Новая", "sections": {"map": "edit", "items": "none"}, "actions": ["keys"]})
        self.assertEqual(made.status_code, 200)
        self.assertEqual(made.json()["sections"]["map"], "edit")
        self.assertEqual(Role.objects.get(name="Новая").rights, {"map": "edit"})
        bad = self.send("post", "team/roles", {"name": "Плохая", "sections": {"map": "all"}})
        self.assertEqual(bad.status_code, 400)

    def test_the_superadmin_adds_and_removes_authors(self):
        self.as_(self.boss)
        self.assertEqual([row["username"] for row in self.client.get("/studio/api/team/candidates?q=play").json()], ["player"])
        added = self.send("put", f"team/authors/{self.player.pk}", {"role": self.writer.pk})
        self.assertEqual(added.status_code, 200)
        self.player.refresh_from_db()
        self.assertTrue(self.player.is_staff)
        self.assertEqual(self.player.role, self.writer)
        self.assertEqual(self.send("delete", f"team/authors/{self.player.pk}").status_code, 204)
        self.player.refresh_from_db()
        self.assertFalse(self.player.is_staff)
        self.assertEqual(self.send("delete", f"team/authors/{self.boss.pk}").status_code, 400)        # себя и суперадмина нельзя

    def test_a_removed_role_leaves_its_authors_looking(self):
        members.delete_role(self.writer)
        self.anna.refresh_from_db()
        self.assertIsNone(self.anna.role)
        self.assertEqual(rights.level_of(self.anna, "items"), rights.READ)
