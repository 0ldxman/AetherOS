"""API конструктора условия доступа: разбор текста в дерево и сборка дерева в текст.

Запуск: python manage.py test studio.tests.test_access_api
"""
from team.testing import full_role
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

API = "/studio/api/access"


@override_settings(FORCE_SCRIPT_NAME=None)
class AccessApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def post(self, path, body):
        response = self.client.post(API + path, data=json.dumps(body), content_type="application/json")
        return response.status_code, response.json()

    def test_text_becomes_a_tree_and_back(self):
        status, parsed = self.post("/parse", {"text": "cardkey and (door or not alarm)"})
        self.assertEqual((status, parsed["ok"]), (200, True))
        self.assertEqual(parsed["tree"], {"all": ["cardkey", {"any": ["door", {"not": "alarm"}]}]})
        self.assertEqual(self.post("/format", {"tree": parsed["tree"]})[1], {"text": "cardkey and (door or not alarm)", "error": ""})

    def test_empty_text_is_an_open_condition_and_a_broken_one_says_why(self):
        self.assertEqual(self.post("/parse", {"text": "  "})[1], {"ok": True, "error": "", "tree": None})
        self.assertEqual(self.post("/format", {"tree": None})[1], {"text": "", "error": ""})
        broken = self.post("/parse", {"text": "a and"})[1]
        self.assertFalse(broken["ok"])
        self.assertTrue(broken["error"])
        self.assertTrue(self.post("/format", {"tree": {"xor": ["a"]}})[1]["error"])

    def test_staff_only(self):
        self.client.logout()
        self.assertIn(self.client.post(API + "/parse", data="{}", content_type="application/json").status_code, (401, 403))
