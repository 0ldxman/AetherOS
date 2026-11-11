"""Поддержка: обращение игрока, ответы команды, заметки, вложения, статусы, уведомления; Студия поверх этого.

Запуск: python manage.py test support
"""
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from django.utils import timezone

from filesystem.testing import make_app
from machines.current import SESSION_KEY
from machines.models import Machine, MachineProfile, Session
from support import desk
from support.models import Ticket
from team.models import Notification
from team.testing import full_role

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


class DeskTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan = User.objects.create_user("ivan", password="pw")
        self.olga = User.objects.create_user("olga", password="pw")
        self.boss = User.objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.mute = User.objects.create_user("mute", password="pw", is_staff=True)                  # без роли: поддержку только смотрит

    def test_ticket_flow_statuses_and_unread(self):
        ticket = desk.open_ticket(self.ivan, subject="Door", category="stuck", text="cannot open", uploads=[SimpleUploadedFile("s.png", PNG, "image/png")])
        self.assertEqual((ticket.status, ticket.messages.get().files.get().is_image), ("new", True))
        self.assertTrue(Notification.objects.filter(user=self.boss, kind="support").exists())
        desk.staff_reply(ticket, self.boss, "internal idea", internal=True)
        self.assertEqual((ticket.status, desk.unread_for(ticket)), ("new", False))               # заметка игроку не видна и статус не меняет
        desk.staff_reply(ticket, self.boss, "try the key")
        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.assignee, desk.unread_for(ticket)), ("waiting", self.boss, True))
        self.assertEqual(desk.pulse(self.ivan)["unread"], 1)
        self.assertEqual([m.text for m in desk.visible(ticket)], ["cannot open", "try the key"])
        desk.seen(ticket)
        self.assertEqual(desk.pulse(self.ivan)["unread"], 0)
        desk.set_status(ticket, "closed")
        desk.player_reply(ticket, self.ivan, "still stuck")
        self.assertEqual(Ticket.objects.get(pk=ticket.pk).status, "open")                          # ответ игрока открывает заново

    def test_limits_and_file_access(self):
        with self.assertRaises(ValidationError):
            desk.open_ticket(self.ivan, subject="x", category="bug", text="")
        with self.assertRaises(ValidationError):
            desk.open_ticket(self.ivan, subject="x", category="bug", text="t", uploads=[SimpleUploadedFile(f"{i}.txt", b"1") for i in range(6)])
        ticket = desk.open_ticket(self.ivan, subject="x", category="weird", text="t", uploads=[SimpleUploadedFile("log.txt", b"log")])
        self.assertEqual(ticket.category, "other")
        note = desk.staff_reply(ticket, self.boss, "", [SimpleUploadedFile("secret.txt", b"x")], internal=True)
        mine, secret = ticket.messages.get(staff=False).files.get(), note.files.get()
        self.assertIsNotNone(desk.file_of(mine.pk, user=self.ivan))
        self.assertIsNone(desk.file_of(mine.pk, user=self.olga))
        self.assertIsNone(desk.file_of(secret.pk, user=self.ivan))
        self.assertIsNotNone(desk.file_of(secret.pk, staff=True))


@override_settings(FORCE_SCRIPT_NAME=None)
class SupportApiTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        User = get_user_model()
        self.ivan = User.objects.create_user("ivan", password="pw")
        self.boss = User.objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(main, label="support", icon="chat", path="/apps/support/")
        profile = MachineProfile.objects.create(machine=main, user=self.ivan, name="Ivan", login="ivan", freq=1)
        self.client.force_login(self.ivan)
        session = self.client.session
        session[SESSION_KEY] = Session.objects.create(user=self.ivan, profile=profile, seen_at=timezone.now()).pk
        session.save()

    def test_player_app_and_studio(self):
        made = self.client.post("/apps/support/api/tickets/new/", {"subject": "Bug", "category": "bug", "text": "it broke",
                                                                   "files": [SimpleUploadedFile("shot.png", PNG, "image/png")]})
        self.assertEqual(made.status_code, 200, made.content)
        ticket_id = made.json()["id"]
        data = self.client.get(f"/apps/support/api/tickets/{ticket_id}/").json()
        picture = data["messages"][0]["files"][0]
        self.assertTrue(picture["image"])
        self.assertEqual(self.client.get(picture["url"])["Content-Type"], "image/png")
        self.assertEqual(self.client.post("/apps/support/api/tickets/new/", {"subject": "", "text": "x"}).status_code, 400)

        studio = self.client_class()
        studio.force_login(self.boss)
        queue = studio.get("/studio/api/support?status=active").json()
        self.assertEqual((queue[0]["player"], queue[0]["waiting_on_team"]), ("ivan", True))
        self.assertEqual(studio.get(f"/studio/api/support/{ticket_id}").json()["context"]["login"], "ivan")
        answered = studio.post(f"/studio/api/support/{ticket_id}/reply", {"text": "fixed", "files": [SimpleUploadedFile("a.txt", b"a")]}).json()
        self.assertEqual((answered["status"], answered["messages"][-1]["files"][0]["name"]), ("waiting", "a.txt"))
        studio.post(f"/studio/api/support/{ticket_id}/reply", {"text": "note", "internal": "true"})
        self.assertEqual(len(self.client.get(f"/apps/support/api/tickets/{ticket_id}/").json()["messages"]), 2)
        closed = studio.put(f"/studio/api/support/{ticket_id}", data=json.dumps({"status": "closed"}), content_type="application/json").json()
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(studio.get(f"/studio/api/support/files/{answered['messages'][-1]['files'][0]['id']}").content, b"a")
        self.assertEqual(self.client.get("/apps/support/api/pulse/").json()["unread"], 0)                 # игрок уже открыл переписку
