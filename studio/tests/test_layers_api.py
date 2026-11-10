"""API конструктора слоёв: каталог, разбор текста в слои и сборка слоёв в текст.

Запуск: python manage.py test studio.tests.test_layers_api
"""
from team.testing import full_role
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

API = "/studio/api/layers"


@override_settings(FORCE_SCRIPT_NAME=None)
class LayersApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def call(self, method, path, body=None):
        response = getattr(self.client, method)(API + path, data=json.dumps(body) if body is not None else None, content_type="application/json")
        return response.status_code, response.json()

    def test_the_catalog_and_the_hook_lists_describe_what_the_form_offers(self):
        status, kinds = self.call("get", "/catalog")
        self.assertEqual(status, 200)
        self.assertIn("encrypted", [row["name"] for row in kinds])
        status, hooks = self.call("get", "/hooks")
        self.assertEqual((status, "remove" in [e["name"] for e in hooks["events"]], "say" in [a["name"] for a in hooks["actions"]]), (200, True, True))

    def test_text_becomes_layers_with_steps_and_back(self):
        text = "> encrypted hunter2 attempts=3\nfile: Заперто\n> shifted skip=4"
        status, found = self.call("post", "/outline", {"text": text})
        self.assertEqual(status, 200)
        self.assertTrue(found["editable"])
        self.assertEqual([row["name"] for row in found["layers"]], ["encrypted", "shifted"])
        self.assertEqual(found["layers"][0]["values"], {"password": "hunter2", "attempts": "3"})
        self.assertEqual(found["layers"][0]["answers"], [{"command": "file", "text": "Заперто"}])
        self.assertEqual(found["steps"], ["ward <файл> hunter2", "blk <файл> skip=4"])
        status, built = self.call("post", "/build", {"preamble": found["preamble"], "layers": found["layers"]})
        self.assertEqual((status, built["text"], built["steps"]), (200, text, found["steps"]))

    def test_a_text_the_form_cannot_edit_says_why(self):
        found = self.call("post", "/outline", {"text": "> mystery 1"})[1]
        self.assertFalse(found["editable"])
        self.assertIn("нет в каталоге", found["unsupported"])
        broken = self.call("post", "/outline", {"text": "> encrypted pw\nнепонятная строка"})[1]
        self.assertFalse(broken["editable"])
        self.assertTrue(broken["problems"])
