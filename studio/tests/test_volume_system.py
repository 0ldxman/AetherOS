"""Системный том: том отличий, который создаётся сам для одной машины; обычные тома такими не бывают.

Запуск: python manage.py test studio.tests.test_volume_system
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.manager.overlay import overlay_for
from filesystem.models import Volume
from machines.models import Machine


@override_settings(FORCE_SCRIPT_NAME=None)
class VolumeSystemTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True))

    def test_the_overlay_of_a_machine_is_a_system_volume_and_a_plain_one_is_not(self):
        machine = Machine.objects.create(name="Core", hostname="core")
        mount, overlay = overlay_for(machine, "/")
        self.assertTrue(overlay.system)
        Volume.objects.create(slug="harbor", label="Архив порта")
        rows = {r["slug"]: r["system"] for r in self.client.get("/studio/api/volumes").json()}
        self.assertEqual(rows, {"core-own": True, "harbor": False})

    def test_a_volume_made_by_hand_is_not_a_system_one(self):
        status = self.client.post("/studio/api/volumes", data=json.dumps({"slug": "hand"}), content_type="application/json").status_code
        self.assertEqual(status, 200)
        self.assertFalse(Volume.objects.get(slug="hand").system)
