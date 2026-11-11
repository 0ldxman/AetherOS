"""Почта на файлах: письма лежат в ящике учётки (/var/mail/<логин>), доставленные игроку только у него, прочитанность своя,
шифрованное письмо закрыто, хук доставляет сразу или с задержкой, приложение отдаёт папки и письма.

Запуск: python manage.py test mail
"""
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from filesystem.models import Item, ItemMember
from filesystem.testing import make_app, make_file
from machines.current import SESSION_KEY
from machines.models import Machine, MachineProfile, Session
from mail import letters
from mail.boxes import Box
from mail.delivery import deliver_by_slug
from mail.models import MailQueue

DOOR = "From: guard@port\nTo: {to}\nSubject: Код двери\nX-Label: work\n\nПривет, {login}. Код в отчёте."


class LettersTests(TestCase):
    def test_headers_and_body_and_placeholders(self):
        letter = letters.parse(letters.fill(DOOR, {"to": "ivan@aether-main", "login": "ivan"}))
        self.assertEqual((letter.sender, letter.to, letter.subject, letter.get("x-label")), ("guard@port", "ivan@aether-main", "Код двери", "work"))
        self.assertEqual(letter.body, "Привет, ivan. Код в отчёте.")
        self.assertEqual(letters.parse("просто текст\nбез заголовков").body, "просто текст\nбез заголовков")
        self.assertEqual(letters.parse("Subject: длинная\n  тема\n\nтело").subject, "длинная тема")
        self.assertEqual(letters.compose([("From", "a@b"), ("Subject", "x")], "тело"), "From: a@b\nSubject: x\n\nтело")


@override_settings(FORCE_SCRIPT_NAME=None)
class BoxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="intercom", icon="mail", path="/apps/mail/")
        cls.ivan = User.objects.create_user("ivan", password="pw")
        cls.olga = User.objects.create_user("olga", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.main, user=cls.ivan, name="Ivan", login="ivan", freq=1)
        cls.shared = MachineProfile.objects.create(machine=cls.main, user=cls.olga, name="Olga", login="olga", freq=2)
        make_file(cls.main, "/var/mail/ivan/inbox/old.msg", body="From: boss@port\nSubject: Старое\n\nулика", format="msg")
        cls.letter = Item.objects.create(slug="door-code", name="Код двери", format="msg", body=DOOR)
        cls.secret = Item.objects.create(slug="sealed", name="Шифровка", format="msg", body="From: x@y\nSubject: Шифр\n\nтайна", state="> encrypted pw")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def box(self, user=None):
        return Box.of_profile(self.profile, user=user or self.ivan)

    def test_an_authored_letter_in_the_box_is_seen_by_whoever_uses_the_account(self):
        rows = self.box().letters_in("inbox")
        self.assertEqual([(r.letter.sender, r.subject, r.read) for r in rows], [("boss@port", "Старое", False)])
        olga_as_ivan = Box.of_profile(self.profile, user=self.olga)
        self.assertEqual(len(olga_as_ivan.letters_in("inbox")), 1)                     # улика в ящике видна любому вошедшему

    def test_a_delivered_letter_is_only_in_the_layer_of_the_player_and_speaks_to_him(self):
        path = self.box().deliver(self.letter)
        self.assertTrue(path.startswith("/var/mail/ivan/inbox/door-code"))
        row = self.box().letter(path)
        self.assertEqual(row.letter.to, self.profile.mail)
        self.assertIn("Привет, ivan.", row.letter.body)
        self.assertIsNotNone(row.arrived)
        self.assertEqual(len(Box.of_profile(self.profile, user=self.olga).letters_in("inbox")), 1)   # у другого игрока только улика

    def test_read_marks_are_per_player_and_trash_moves_the_letter(self):
        path = self.box().deliver(self.letter)
        self.box().mark(path)
        self.assertTrue(self.box().letter(path).read)
        self.assertEqual(self.box().unread(), 1)                                          # осталась улика
        trashed = self.box().trash(path)
        self.assertTrue(trashed.startswith("/var/mail/ivan/trash/"))
        self.assertTrue(self.box().letter(trashed).read)                                 # отметка переехала вместе с письмом
        back = self.box().restore(trashed)
        self.assertTrue(back.startswith("/var/mail/ivan/inbox/"))

    def test_an_encrypted_letter_shows_its_headers_but_not_the_body(self):
        path = self.box().deliver(self.secret)
        row = self.box().letter(path)
        self.assertTrue(row.locked)
        self.assertEqual((row.letter.sender, row.letter.body), ("x@y", ""))

    def test_the_hook_delivers_now_or_later_to_the_current_account(self):
        Session.objects.create(user=self.ivan, profile=self.profile, seen_at=timezone.now())
        now = deliver_by_slug(self.ivan, "door-code")
        self.assertTrue(now.delivered and now.immediate)
        later = deliver_by_slug(self.ivan, "door-code", delay=60)
        self.assertFalse(later.immediate)
        self.assertEqual(MailQueue.objects.count(), 1)
        self.assertEqual(len(self.box().letters_in("inbox")), 2)
        with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(seconds=120)):
            self.assertEqual(len(self.box().letters_in("inbox")), 3)                    # подошёл срок: письмо из очереди пришло
        self.assertFalse(MailQueue.objects.exists())
        self.assertFalse(deliver_by_slug(self.ivan, "ghost").delivered)

    def test_attachments_are_members_of_the_letter(self):
        report = Item.objects.create(slug="report", name="report.txt", body="отчёт")
        ItemMember.objects.create(archive=self.letter, path="report.txt", item=report)
        row = self.box().letter(self.box().deliver(self.letter))
        self.assertEqual([m.path for m in row.attachments], ["report.txt"])


@override_settings(FORCE_SCRIPT_NAME=None)
class MailAppTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="intercom", icon="mail", path="/apps/mail/")
        make_app(cls.main, label="console", icon="terminal", path="/apps/terminal/")
        cls.ivan = get_user_model().objects.create_user("ivan", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.main, user=cls.ivan, name="Ivan", login="ivan", freq=1)
        make_file(cls.main, "/var/mail/ivan/inbox/hello.msg", body="From: boss@port\nSubject: Привет\nX-Label: work\n\nдобро пожаловать", format="msg")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.ivan)
        session = self.client.session
        session[SESSION_KEY] = Session.objects.create(user=self.ivan, profile=self.profile, seen_at=timezone.now()).pk
        session.save()

    def post(self, name, body):
        return self.client.post(f"/apps/mail/api/{name}/", data=json.dumps(body), content_type="application/json")

    def test_the_list_the_letter_unread_and_trash(self):
        data = self.client.get("/apps/mail/api/messages/").json()
        self.assertEqual(data["address"], self.profile.mail)
        row = data["messages"][0]
        self.assertEqual((row["sender"], row["subject"], row["unread"], row["label"], row["folder"]), ("boss@port", "Привет", True, "work", "inbox"))
        letter = self.client.get("/apps/mail/api/message/", {"path": row["id"]}).json()
        self.assertEqual(letter["body"], "добро пожаловать")
        self.assertFalse(self.client.get("/apps/mail/api/messages/").json()["messages"][0]["unread"])
        self.post("message/unread", {"path": row["id"]})
        self.assertEqual(self.client.get("/apps/mail/api/pulse/").json()["unread"], 1)
        moved = self.post("message/trash", {"path": row["id"]}).json()["path"]
        self.assertEqual(self.client.get("/apps/mail/api/messages/").json()["messages"][0]["folder"], "trash")
        self.post("message/trash", {"path": moved})                                     # из корзины обратно
        self.assertEqual(self.client.get("/apps/mail/api/messages/").json()["messages"][0]["folder"], "inbox")
        self.assertEqual(self.client.get("/apps/mail/api/message/", {"path": "/etc/hosts"}).status_code, 404)   # не из ящика

    def test_an_attachment_opens_in_a_window_from_the_mail(self):
        letter = Item.objects.create(slug="with-report", name="r.msg", format="msg", body="From: boss@port\nSubject: Отчёт\n\nсм. вложение")
        ItemMember.objects.create(archive=letter, path="report.txt", item=Item.objects.create(slug="report", name="report.txt", body="отчёт"))
        path = Box.of_profile(self.profile, self.ivan).deliver(letter)
        found = self.client.get("/apps/mail/api/message/", {"path": path}).json()["attachments"][0]
        window = self.client.get(found["open"]).json()
        self.assertEqual(window["title"], "report.txt")
        self.assertContains(self.client.get(window["url"]), "")                         # вьювер находит файл по адресу ?mail=
        self.assertEqual(self.client.get("/apps/mail/api/attachment/", {"path": path + "/other.txt"}).status_code, 404)
        self.assertEqual(self.client.get("/apps/mail/api/attachment/", {"path": "/etc/hosts"}).status_code, 404)

    def test_cnt_on_a_letter_opens_it_in_the_mail_app(self):
        response = self.client.post("/apps/terminal/execute/", data=json.dumps({"command": "cnt /var/mail/ivan/inbox/hello.msg"}), content_type="application/json")
        window = response.json()["window"]
        self.assertTrue(window["url"].startswith("/apps/mail/?file="), window)
        page = self.client.get(window["url"])
        self.assertContains(page, 'data-file="/var/mail/ivan/inbox/hello.msg"')
