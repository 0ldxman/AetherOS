"""Лента изменений и проверка версии: запись каждого изменения, номер в ответе, конфликт и сохранение поверх.

Запуск: python manage.py test team
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from machines.models import Machine
from team.models import Change
from team.testing import full_role


@override_settings(FORCE_SCRIPT_NAME=None)
class ChangesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.anna = User.objects.create_user("anna", password="pw", is_staff=True, role=full_role())
        cls.olga = User.objects.create_user("olga", password="pw", is_staff=True, role=full_role())
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.anna)

    def put(self, path, body, **headers):
        return self.client.put(f"/studio/api/{path}", data=json.dumps(body), content_type="application/json", headers=headers)

    def overview(self):
        response = self.client.get(f"/studio/api/machines/{self.machine.pk}")
        return response.json(), response["X-Version"]

    def header(self, data):
        return {key: data[key] for key in ("hostname", "name", "system", "status", "address", "serial", "host_key", "note")}

    def test_a_change_is_written_with_who_what_and_a_link(self):
        data, _ = self.overview()
        response = self.put(f"machines/{self.machine.pk}", {**self.header(data), "name": "Главная"})
        self.assertEqual(response.status_code, 200, response.content)
        change = Change.objects.get()
        self.assertEqual((change.username, change.action, change.kind, change.label, change.section),
                         ("anna", "update", "Машина", "aether-main", "machines"))
        self.assertEqual(change.link, f"#/machines/{self.machine.pk}")
        self.assertEqual(response["X-Version"], str(change.pk))
        feed = self.client.get("/studio/api/team/changes").json()
        self.assertEqual(feed[0]["action_label"], "изменение")

    def test_a_save_over_a_newer_change_of_another_author_is_a_conflict_unless_forced(self):
        data, version = self.overview()
        body = {**self.header(data), "name": "Моя"}
        self.client.force_login(self.olga)
        self.assertEqual(self.put(f"machines/{self.machine.pk}", {**body, "name": "Ольгина"}, **{"X-Base-Version": version}).status_code, 200)
        self.client.force_login(self.anna)
        stale = self.put(f"machines/{self.machine.pk}", body, **{"X-Base-Version": version})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["by"], "olga")
        self.assertIn("уже изменили (olga", stale.json()["detail"])
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.name, "Ольгина")
        forced = self.put(f"machines/{self.machine.pk}", body, **{"X-Base-Version": version, "X-Force": "1"})
        self.assertEqual(forced.status_code, 200)
        # своё сохранение с новым номером проходит
        again = self.put(f"machines/{self.machine.pk}", {**body, "name": "Снова"}, **{"X-Base-Version": forced["X-Version"]})
        self.assertEqual(again.status_code, 200)

    def test_a_change_of_another_entity_is_not_a_conflict(self):
        other = Machine.objects.create(name="Core", hostname="aether-core")
        data, version = self.overview()
        self.client.force_login(self.olga)
        other_data = self.client.get(f"/studio/api/machines/{other.pk}").json()
        self.put(f"machines/{other.pk}", {**self.header(other_data), "name": "Ядро"})
        self.client.force_login(self.anna)
        response = self.put(f"machines/{self.machine.pk}", {**self.header(data), "name": "Моя"}, **{"X-Base-Version": version})
        self.assertEqual(response.status_code, 200)

    def test_reading_previews_and_refusals_leave_no_trace(self):
        self.client.get("/studio/api/machines")
        self.client.post("/studio/api/machines/randomart", data="{}", content_type="application/json")
        self.put("machines/999999", {"hostname": "x"})
        self.assertFalse(Change.objects.exists())

    def test_a_created_entity_is_named_and_a_deleted_one_keeps_a_snapshot(self):
        made = self.client.post("/studio/api/team/roles", data=json.dumps({"name": "Тест"}), content_type="application/json")
        self.assertEqual(made.status_code, 403)                              # командой правит суперадмин
        self.anna.is_superuser = True
        self.anna.save()
        made = self.client.post("/studio/api/team/roles", data=json.dumps({"name": "Тест"}), content_type="application/json")
        role_id = made.json()["id"]
        created = Change.objects.get()
        self.assertEqual((created.action, created.kind, created.label, created.path), ("create", "Роль", "Тест", f"team/roles/{role_id}"))
        self.client.delete(f"/studio/api/team/roles/{role_id}")
        deleted = Change.objects.order_by("-pk").first()
        self.assertEqual((deleted.action, deleted.label), ("delete", "Тест"))
        self.assertEqual(deleted.snapshot["fields"]["name"], "Тест")
