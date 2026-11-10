"""Удаление в менеджере тома возвращает снимок, по нему «Отменить» возвращает всё на место.

Запуск: python manage.py test studio.tests.test_undo_api
"""
from team.testing import full_role
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.manager import filemanager
from filesystem.models import Placement, Volume

API = "/studio/api/volumes"


@override_settings(FORCE_SCRIPT_NAME=None)
class UndoApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        cls.volume = Volume.objects.create(slug="undo-api")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def post(self, path, body):
        response = self.client.post(f"{API}/{self.volume.pk}{path}", data=json.dumps(body), content_type="application/json")
        return response.status_code, response.json()

    def test_delete_gives_a_snapshot_and_restore_brings_the_files_back(self):
        folder = filemanager.new_folder(self.volume, None, "docs")
        filemanager.new_text_file(self.volume, folder.pk, "a.txt", "текст")
        status, deleted = self.post("/delete", {"ids": [folder.pk]})
        self.assertEqual((status, deleted["count"], len(deleted["undo"])), (200, 1, 2))
        self.assertEqual(Placement.objects.filter(volume=self.volume).count(), 0)
        status, restored = self.post("/restore", {"undo": deleted["undo"]})
        self.assertEqual((status, restored["count"]), (200, 2))
        self.assertEqual(Placement.objects.get(volume=self.volume, name="a.txt").content, "текст")

    def test_a_restore_that_cannot_be_exact_is_refused_with_a_reason(self):
        file = filemanager.new_text_file(self.volume, None, "b.txt", "1")
        undo = self.post("/delete", {"ids": [file.pk]})[1]["undo"]
        filemanager.new_text_file(self.volume, None, "b.txt", "2")
        status, error = self.post("/restore", {"undo": undo})
        self.assertEqual(status, 400)
        self.assertIn("уже есть", error["detail"])
