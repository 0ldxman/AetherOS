"""Форум в Студии: пространства, привязка машин, разделы с условиями, модерация, голос персонажа."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from forum import logic
from forum.models import Post, Section, Space, Topic
from machines.models import Machine
from team.testing import full_role


class ForumStudioTests(TestCase):
    def setUp(self):
        self.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.client.force_login(self.boss)
        self.machine = Machine.objects.create(name="Core", hostname="aether-core")

    def call(self, method, path, body=None):
        response = getattr(self.client, method)(f"/studio/api/forum{path}", data=json.dumps(body) if body is not None else None, content_type="application/json")
        return response.status_code, (response.json() if response.content else None)

    def make_space(self):
        status, data = self.call("post", "/spaces", {"slug": "relay", "title": "Relay", "machines": [self.machine.pk], "read_if": "mask"})
        self.assertEqual(status, 200)
        return data

    def test_space_create_validates_and_binds_machines(self):
        self.assertEqual(self.call("post", "/spaces", {"slug": "A", "title": "x"})[1]["fields"].keys(), {"slug"})
        self.assertIn("title", self.call("post", "/spaces", {"slug": "okay", "title": " "})[1]["fields"])
        data = self.make_space()
        self.assertEqual((data["machines"], data["read_if"]), ([self.machine.pk], "mask"))
        self.assertEqual(self.call("post", "/spaces", {"slug": "relay", "title": "Dup"})[0], 400)
        self.assertEqual(Space.objects.get(slug="relay").read_if, "mask")
        rows = self.call("get", "/spaces")[1]
        self.assertEqual([(r["slug"], r["machines"]) for r in rows], [("relay", 1)])

    def test_bad_condition_is_reported_on_its_field(self):
        status, data = self.call("post", "/spaces", {"slug": "relay", "title": "R", "read_if": "a and"})
        self.assertEqual(status, 400)
        self.assertIn("read_if", data["fields"])

    def test_sections_tree_rules_and_loop_protection(self):
        self.make_space()
        status, a = self.call("post", "/spaces/relay/sections", {"title": "General"})
        status, b = self.call("post", "/spaces/relay/sections", {"title": "Ciphers", "parent": a["id"], "write": "authors", "read_if": "cipher"})
        self.assertEqual((b["parent"], b["write"], b["read_if"]), (a["id"], "authors", "cipher"))
        status, data = self.call("put", f"/sections/{a['id']}", {"title": "General", "parent": b["id"]})
        self.assertEqual(status, 400)
        self.assertIn("parent", data["fields"])
        self.assertEqual(self.call("post", "/spaces/relay/sections", {"title": "x", "write": "everyone"})[0], 400)
        detail = self.call("get", "/spaces/relay")[1]
        self.assertEqual([s["title"] for s in detail["sections"]], ["Ciphers", "General"])

    def test_foreign_parent_is_refused(self):
        self.make_space()
        self.call("post", "/spaces", {"slug": "other", "title": "Other"})
        foreign = self.call("post", "/spaces/other/sections", {"title": "Alien"})[1]
        status, data = self.call("post", "/spaces/relay/sections", {"title": "x", "parent": foreign["id"]})
        self.assertEqual((status, list(data["fields"])), (400, ["parent"]))

    def test_author_voice_flags_and_moderation(self):
        self.make_space()
        section = self.call("post", "/spaces/relay/sections", {"title": "General"})[1]
        status, topic = self.call("post", "/topics", {"section": section["id"], "name": "SYSOP", "title": "Rules", "text": "Be kind"})
        self.assertEqual((status, topic["kind"], topic["posts"][0]["name"]), (200, "character", "SYSOP"))
        self.assertEqual(self.call("post", "/topics", {"section": section["id"], "name": " ", "title": "x", "text": "y"})[0], 400)
        status, topic = self.call("post", f"/topics/{topic['id']}/posts", {"name": "SENSOR", "text": "act 2", "kind": "system"})
        self.assertEqual(topic["posts"][1]["kind"], "system")
        status, flagged = self.call("put", f"/topics/{topic['id']}", {"pinned": True, "locked": True})
        self.assertEqual((flagged["pinned"], flagged["locked"]), (True, True))
        reply = topic["posts"][1]
        status, after = self.call("post", f"/posts/{reply['id']}/hide", {"reason": "spam"})
        self.assertEqual((after["posts"][1]["hidden"], after["posts"][1]["hidden_reason"]), (True, "spam"))
        status, after = self.call("post", f"/posts/{reply['id']}/restore")
        self.assertFalse(after["posts"][1]["hidden"])

    def test_hidden_topics_and_search_listing(self):
        self.make_space()
        section = Section.objects.create(space=Space.objects.get(slug="relay"), title="General")
        a = logic.author_topic(section, "SYSOP", "Alpha", "first text")
        b = logic.author_topic(section, "SYSOP", "Beta", "needle inside")
        logic.hide_post(b.posts.get(root=True), "off-topic")
        self.assertEqual([t["title"] for t in self.call("get", "/spaces/relay/topics")[1]], ["Alpha"])
        self.assertEqual([t["title"] for t in self.call("get", "/spaces/relay/topics?hidden=true")[1]], ["Beta"])
        self.assertEqual([t["title"] for t in self.call("get", "/spaces/relay/topics?q=first")[1]], ["Alpha"])

    def test_delete_space_removes_everything_and_needs_the_delete_right(self):
        self.make_space()
        self.assertEqual(self.call("delete", "/spaces/relay")[0], 204)
        self.assertFalse(Space.objects.exists())
        reader = get_user_model().objects.create_user("reader", password="pw", is_staff=True)
        self.client.force_login(reader)
        self.assertEqual(self.call("get", "/spaces")[0], 200)
        self.assertEqual(self.call("post", "/spaces", {"slug": "nope", "title": "x"})[0], 403)
