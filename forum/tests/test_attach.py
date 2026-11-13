"""Вложения форума: что можно приложить, снимок, сохранение на диск читателя."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.machine_view import view_for
from filesystem.testing import embed_key, give_keys, make_app, make_file
from forum import attach, logic
from forum.models import Attachment, Section, Space
from machines.current import SESSION_KEY
from machines.models import Machine, Session
from mail.boxes import Box


class AttachTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(name="Home", hostname="aether-home")
        self.ivan = get_user_model().objects.create_user("ivan")
        make_file(self.machine, "/home/ivan/note.txt", body="my note")
        make_file(self.machine, "/home/ivan/vault.key", key="vault")
        carrier = make_file(self.machine, "/home/ivan/carrier.txt", body="with a key inside")
        embed_key(carrier.item, "inner")
        make_file(self.machine, "/home/ivan/big.txt", body="x" * (attach.MAX_TEXT + 1))
        make_file(self.machine, "/home/ivan/dir", directory=True)
        self.view = view_for(self.machine, self.ivan, login="ivan")

    def entry(self, name):
        return self.view.get(f"/home/ivan/{name}")

    def test_a_readable_file_becomes_a_snapshot(self):
        found = attach.snapshot(self.entry("note.txt"), set())
        self.assertEqual((found["name"], found["size"]), ("note.txt", 7))
        self.assertIsNotNone(found["item"])

    def test_keys_folders_and_big_files_are_refused(self):
        for name in ("vault.key", "carrier.txt", "dir", "big.txt"):
            with self.assertRaises(logic.ForumError, msg=name):
                attach.snapshot(self.entry(name), set())
        with self.assertRaises(logic.ForumError):
            attach.snapshot(None, set())

    def test_saving_puts_a_copy_in_the_readers_home_and_does_not_overwrite(self):
        space = Space.objects.create(slug="net", title="Net")
        section = Section.objects.create(space=space, title="General")
        topic = logic.start_topic(section, self.ivan, "Hi", "see file", set())
        post = topic.posts.get(root=True)
        [saved] = attach.attach(post, [attach.snapshot(self.entry("note.txt"), set())])
        reader = get_user_model().objects.create_user("anna")
        make_file(self.machine, "/home/anna/readme", body="x")
        box = Box(self.machine, "anna", "anna@home", user=reader)
        first = attach.save_to_disk(box, saved)
        second = attach.save_to_disk(box, saved)
        self.assertEqual((first, second), ("/home/anna/note.txt", "/home/anna/note-2.txt"))
        self.assertEqual(box.view.get(first).body, "my note")
        guest = Box(self.machine, "witness", "witness@home", session_key="s")
        with self.assertRaises(logic.ForumError):
            attach.save_to_disk(guest, saved)

    def test_limit_per_post(self):
        space = Space.objects.create(slug="net", title="Net")
        topic = logic.author_topic(Section.objects.create(space=space, title="G"), "SYSOP", "T", "t")
        shot = attach.snapshot(self.entry("note.txt"), set())
        with self.assertRaises(logic.ForumError):
            attach.attach(topic.posts.get(root=True), [shot] * (attach.MAX_PER_POST + 1))


@override_settings(FORCE_SCRIPT_NAME=None)
class AttachViewTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.ivan = get_user_model().objects.create_user("ivan")
        held = give_keys(self.ivan)
        session = self.client.session
        session.update(held)
        session.save()
        self.machine = Session.objects.get(pk=held[SESSION_KEY]).profile.machine
        make_app(self.machine, label="forum", icon="chat", path="/apps/forum/")
        self.space = Space.objects.create(slug="net", title="Net")
        self.space.machines.add(self.machine)
        self.general = Section.objects.create(space=self.space, title="General")
        make_file(self.machine, "/home/keys/note.txt", body="my note")
        self.client.force_login(self.ivan)
        session = self.client.session
        session.update(held)
        session.save()

    def post(self, name, body):
        response = self.client.post(reverse(f"forum:{name}"), data=json.dumps(body), content_type="application/json")
        return response.status_code, response.json()

    def test_file_picker_lists_the_home_folder(self):
        data = self.client.get(reverse("forum:files")).json()
        self.assertIn("note.txt", [row["name"] for row in data["entries"]])

    def test_topic_with_a_file_then_save_it(self):
        status, made = self.post("new_topic", {"section": self.general.pk, "title": "Look", "text": "file", "attachments": ["/home/keys/note.txt"]})
        self.assertEqual(status, 200)
        thread = self.client.get(reverse("forum:topic", args=[made["id"]])).json()
        [file] = thread["posts"][0]["files"]
        self.assertEqual(file["name"], "note.txt")
        status, saved = self.post("save_attachment", {"attachment": file["id"]})
        self.assertEqual((status, saved["path"]), (200, "/home/keys/note-2.txt"))

    def test_a_bad_attachment_stops_the_post(self):
        status, data = self.post("new_topic", {"section": self.general.pk, "title": "Look", "text": "file", "attachments": ["/home/keys/nope"]})
        self.assertEqual(status, 403)
        self.assertFalse(self.general.topics.exists())

    def test_hidden_post_files_are_not_listed_and_cannot_be_saved(self):
        topic = logic.start_topic(self.general, self.ivan, "T", "t", set())
        reply = logic.reply(topic, self.ivan, "r", set())
        note = view_for(self.machine, self.ivan, login="keys").get("/home/keys/note.txt")
        [saved] = attach.attach(reply, [attach.snapshot(note, set())])
        logic.hide_post(reply, "x")
        thread = self.client.get(reverse("forum:topic", args=[topic.pk])).json()
        self.assertEqual(thread["posts"][1]["files"], [])
        response = self.client.post(reverse("forum:save_attachment"), data=json.dumps({"attachment": saved.pk}), content_type="application/json")
        self.assertEqual(response.status_code, 404)
