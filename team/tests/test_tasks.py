"""Задачи и уведомления: несколько исполнителей, приоритет 1–10, ссылки на сущности, доска статусов, задача из ветки,
уведомления о назначении, упоминании и сроке.

Запуск: python manage.py test team
"""
import datetime as dt
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from machines.models import Machine
from team.models import Change, Notification, Task


@override_settings(FORCE_SCRIPT_NAME=None)
class TasksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.anna = User.objects.create_user("anna", password="pw", is_staff=True)
        cls.olga = User.objects.create_user("olga", password="pw", is_staff=True)
        cls.oleg = User.objects.create_user("oleg", password="pw", is_staff=True)
        cls.player = User.objects.create_user("ivan", password="pw")
        cls.machine = Machine.objects.create(name="Core", hostname="aether-core")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.anna)

    def send(self, method, path, body=None):
        return getattr(self.client, method)(f"/studio/api{path}", data=json.dumps(body or {}), content_type="application/json")

    def make(self, **fields):
        body = {"title": "Загадка порта", "priority": 8, "assignees": [self.olga.pk, self.oleg.pk], "links": [f"machines/{self.machine.pk}"],
                "labels": ["Загадка", "порт"], **fields}
        response = self.send("post", "/tasks", body)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_a_task_with_several_assignees_a_priority_and_a_link(self):
        task = self.make()
        self.assertEqual(task["assignee_names"], ["olga", "oleg"])
        self.assertEqual(task["priority"], 8)
        self.assertEqual(task["labels"], ["загадка", "порт"])
        self.assertEqual(task["links"], [{"target": f"machines/{self.machine.pk}", "kind": "Машина", "label": "aether-core", "link": f"#/machines/{self.machine.pk}"}])
        self.assertEqual(self.send("post", "/tasks", {"title": "x", "priority": 11}).status_code, 400)
        self.assertEqual(self.send("post", "/tasks", {"title": "x", "assignees": [self.player.pk]}).status_code, 400)   # игрок не исполнитель
        about = self.client.get(f"/studio/api/tasks?target=machines/{self.machine.pk}").json()
        self.assertEqual([t["title"] for t in about], ["Загадка порта"])
        self.assertEqual(Change.objects.filter(kind="Задача", action="create").count(), 1)

    def test_assigned_authors_are_notified_once_and_read_it(self):
        task = self.make()
        self.send("put", f"/tasks/{task['id']}", {"title": "Загадка порта", "assignees": [self.olga.pk, self.oleg.pk]})   # тот же состав
        self.assertEqual(Notification.objects.filter(user=self.olga, kind="assigned").count(), 1)
        self.assertFalse(Notification.objects.filter(user=self.anna).exists())                                         # себе не шлётся
        self.client.force_login(self.olga)
        inbox = self.client.get("/studio/api/notifications").json()
        self.assertEqual(inbox["unread"], 1)
        self.assertIn("назначил", inbox["rows"][0]["text"])
        self.assertEqual(self.send("post", "/notifications/read", {}).json()["unread"], 0)

    def test_the_board_moves_a_task_and_deadlines_are_reminded(self):
        task = self.make(due=str(timezone.localdate() - dt.timedelta(days=1)))
        self.assertTrue(task["overdue"])
        moved = self.send("post", f"/tasks/{task['id']}/move", {"status": "review"}).json()
        self.assertEqual(moved["status_label"], "На проверке")
        self.client.force_login(self.olga)
        kinds = [row["kind"] for row in self.client.get("/studio/api/notifications").json()["rows"]]
        self.assertIn("overdue", kinds)
        self.client.get("/studio/api/notifications")
        self.assertEqual(Notification.objects.filter(user=self.olga, kind="overdue").count(), 1)                        # раз в день
        self.send("post", f"/tasks/{task['id']}/move", {"status": "done"})
        self.assertEqual(self.client.get("/studio/api/tasks?overdue=true").json(), [])

    def test_a_task_from_a_thread_and_a_mention_notification(self):
        thread = self.send("post", "/comments", {"target": f"machines/{self.machine.pk}", "text": "Пароль reader слишком простой @olga"}).json()
        self.assertTrue(Notification.objects.filter(user=self.olga, kind="mention").exists())
        task = self.send("post", "/tasks/from-thread", {"thread": thread["id"]}).json()
        self.assertEqual(task["title"], "Пароль reader слишком простой @olga")
        self.assertEqual(task["links"][0]["target"], f"machines/{self.machine.pk}")
        replies = self.client.get(f"/studio/api/comments?target=machines/{self.machine.pk}").json()[0]["messages"]
        self.assertIn(f"#/tasks/{task['id']}", replies[-1]["text"])

    def test_only_the_author_or_the_superadmin_deletes(self):
        task = self.make()
        self.client.force_login(self.olga)
        self.assertEqual(self.send("delete", f"/tasks/{task['id']}").status_code, 400)
        self.client.force_login(self.anna)
        self.assertEqual(self.send("delete", f"/tasks/{task['id']}").status_code, 204)
        self.assertFalse(Task.objects.exists())
