"""Обсуждения: ветки на сущности, ответы, упоминания, «решено», свои сообщения, входящие на Главной.

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
class CommentsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.anna = User.objects.create_user("anna", password="pw", is_staff=True, role=full_role())
        cls.olga = User.objects.create_user("olga", password="pw", is_staff=True)          # без роли: только смотрит, но пишет
        cls.player = User.objects.create_user("ivan", password="pw")
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        cls.target = f"machines/{cls.machine.pk}"

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def as_(self, user):
        self.client.force_login(user)

    def send(self, method, path, body=None):
        return getattr(self.client, method)(f"/studio/api/comments{path}", data=json.dumps(body or {}), content_type="application/json")

    def test_a_thread_with_a_reply_a_mention_and_the_label_of_the_entity(self):
        self.as_(self.anna)
        thread = self.send("post", "", {"target": self.target, "text": "Проверь пароль, @olga и @ivan"}).json()
        self.assertEqual(thread["messages"][0]["mentions"], ["olga"])                    # игрока не упоминают
        self.as_(self.olga)
        thread = self.send("post", "", {"text": "Сделано", "parent": thread["id"]}).json()
        self.assertEqual([m["username"] for m in thread["messages"]], ["anna", "olga"])
        listed = self.client.get(f"/studio/api/comments?target={self.target}").json()
        self.assertEqual(len(listed), 1)
        inbox = self.client.get("/studio/api/comments/inbox").json()
        self.assertEqual((inbox["rows"][0]["kind"], inbox["rows"][0]["label"], inbox["rows"][0]["link"]),
                         ("Машина", "aether-main", f"#/machines/{self.machine.pk}"))
        self.assertTrue(inbox["rows"][0]["mentioned"])
        self.assertFalse(inbox["rows"][0]["waiting"])                                    # последней писала она сама
        self.as_(self.anna)
        self.assertTrue(self.client.get("/studio/api/comments/inbox").json()["rows"][0]["waiting"])
        self.assertFalse(Change.objects.exists())                                         # обсуждения не пишутся в ленту изменений

    def test_resolve_reopen_by_a_reply_and_counts(self):
        self.as_(self.anna)
        thread = self.send("post", "", {"target": self.target, "text": "Вопрос"}).json()
        self.assertEqual(self.client.get(f"/studio/api/comments/counts?targets={self.target}").json(), {self.target: 1})
        resolved = self.send("post", f"/{thread['id']}/resolve", {"resolved": True}).json()
        self.assertEqual(resolved["resolved_by"], "anna")
        self.assertEqual(self.client.get(f"/studio/api/comments/counts?targets={self.target}").json(), {})
        reopened = self.send("post", "", {"text": "Ещё вопрос", "parent": thread["id"]}).json()
        self.assertIsNone(reopened["resolved_at"])

    def test_only_own_messages_are_edited_and_deleted(self):
        self.as_(self.anna)
        thread = self.send("post", "", {"target": self.target, "text": "Моё"}).json()
        message = thread["messages"][0]["id"]
        self.as_(self.olga)
        self.assertEqual(self.send("put", f"/{message}", {"text": "Чужое"}).status_code, 400)
        self.assertEqual(self.send("delete", f"/{message}").status_code, 400)
        self.as_(self.anna)
        self.assertEqual(self.send("put", f"/{message}", {"text": "Исправлено"}).json()["text"], "Исправлено")
        self.assertEqual(self.send("delete", f"/{message}").status_code, 204)

    def test_empty_text_and_players_are_refused(self):
        self.as_(self.anna)
        self.assertEqual(self.send("post", "", {"target": self.target, "text": "  "}).status_code, 400)
        self.as_(self.player)
        self.assertEqual(self.client.get(f"/studio/api/comments?target={self.target}").status_code, 401)
