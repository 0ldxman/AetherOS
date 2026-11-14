"""Словарь действий для Студии: действия с полями и подсказки для полей."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from filesystem.testing import key_item
from team.testing import full_role


class EngineApiTests(TestCase):
    def setUp(self):
        self.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.client.force_login(self.boss)

    def test_catalog_lists_actions_and_picks(self):
        key_item("dock")
        response = self.client.get("/studio/api/engine/catalog")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("world_flag", [a["name"] for a in data["actions"]])
        self.assertIn("dock", [o["value"] for o in data["picks"]["key"]])
