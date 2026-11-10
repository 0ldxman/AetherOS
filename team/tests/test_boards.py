"""Доски: основная есть сразу, новые заводит любой автор, удаляет создатель или суперадмин; поиск сущностей; документ доски
хранится и без «несохранённого».

Запуск: python manage.py test team
"""
import json

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from machines.models import Machine
from team import collab
from team.models import Board, Draft


@override_settings(FORCE_SCRIPT_NAME=None)
class BoardsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.anna = User.objects.create_user("anna", password="pw", is_staff=True)                # без роли: доски всё равно её
        cls.olga = User.objects.create_user("olga", password="pw", is_staff=True)
        Machine.objects.create(name="Core", hostname="aether-core")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.anna)

    def send(self, method, path, body=None):
        return getattr(self.client, method)(f"/studio/api/boards{path}", data=json.dumps(body or {}), content_type="application/json")

    def test_the_main_board_exists_and_cannot_be_deleted(self):
        rows = self.client.get("/studio/api/boards").json()
        main = next(row for row in rows if row["main"])
        self.assertFalse(main["deletable"])
        self.assertEqual(self.send("delete", f"/{main['id']}").status_code, 400)

    def test_an_author_makes_renames_and_deletes_own_board_only(self):
        made = self.send("post", "", {"title": "Загадка порта"}).json()
        self.assertTrue(made["deletable"])
        self.assertEqual(self.send("put", f"/{made['id']}", {"title": "Порт"}).json()["title"], "Порт")
        self.client.force_login(self.olga)
        self.assertEqual(self.send("delete", f"/{made['id']}").status_code, 400)
        self.client.force_login(self.anna)
        self.assertEqual(self.send("delete", f"/{made['id']}").status_code, 204)
        self.assertFalse(Board.objects.filter(pk=made["id"]).exists())

    def test_entities_are_found_by_name_for_cards(self):
        found = self.client.get("/studio/api/boards/entities?q=core").json()
        self.assertIn({"kind": "Машина", "label": "aether-core", "link": f"#/machines/{Machine.objects.get().pk}"}, found)

    def test_the_document_of_a_board_is_kept_without_unsaved_changes(self):
        board = Board.objects.get(main=True)

        async def run():
            found = await collab.room(board.room)
            found.doc.get("elements", type=__import__("pycrdt").Map)["a"] = {"id": "a", "version": 1}
            await found.flush()
            collab._rooms.pop(board.room, None)
        async_to_sync(run)()
        self.assertTrue(Draft.objects.filter(room=board.room).exists())
