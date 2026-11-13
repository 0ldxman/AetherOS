"""Приложение «форум» у игрока: список пространств машины, разделы, темы, ответы, доступ."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import make_app
from forum import logic
from forum.models import Section, Space
from machines.models import Machine


@override_settings(FORCE_SCRIPT_NAME=None)
class ForumAppTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(self.main, label="forum", icon="chat", path="/apps/forum/")
        self.space = Space.objects.create(slug="net", title="Net", about="Old node network")
        self.space.machines.add(self.main)
        self.general = Section.objects.create(space=self.space, title="General")
        self.secret = Section.objects.create(space=self.space, title="Secret", read_if="mask")
        self.ivan = get_user_model().objects.create_user("ivan")
        self.client.force_login(self.ivan)

    def get(self, name, *args):
        response = self.client.get(reverse(f"forum:{name}", args=args))
        return response.status_code, (response.json() if response["Content-Type"].startswith("application/json") else None)

    def post(self, name, body):
        response = self.client.post(reverse(f"forum:{name}"), data=json.dumps(body), content_type="application/json")
        return response.status_code, response.json()

    def test_page_and_spaces_of_this_machine(self):
        self.assertEqual(self.client.get(reverse("forum:index")).status_code, 200)
        status, data = self.get("spaces")
        self.assertEqual((status, [s["slug"] for s in data["spaces"]]), (200, ["net"]))
        self.assertEqual(data["callsign"], logic.author_name(self.ivan))

    def test_a_space_of_another_machine_is_not_found(self):
        other = Space.objects.create(slug="far", title="Far")
        other.machines.add(Machine.objects.create(name="Null", hostname="aether-null"))
        self.assertEqual(self.get("space", "far")[0], 404)

    def test_tree_hides_closed_sections_until_the_key_is_held(self):
        status, data = self.get("space", "net")
        self.assertEqual([n["title"] for n in data["tree"]], ["General"])
        self.assertEqual(self.get("section", self.secret.pk)[0], 404)

    def test_topic_and_reply_round_trip(self):
        status, made = self.post("new_topic", {"section": self.general.pk, "title": "Hi", "text": "hello **all**"})
        self.assertEqual(status, 200)
        status, listing = self.get("section", self.general.pk)
        self.assertEqual([(t["title"], t["replies"]) for t in listing["topics"]], [("Hi", 0)])
        self.assertTrue(listing["can_write"])
        status, thread = self.get("topic", made["id"])
        root = thread["posts"][0]
        self.assertEqual((root["root"], root["text"]), (True, "hello **all**"))
        status, reply = self.post("new_post", {"topic": made["id"], "parent": root["id"], "text": "welcome"})
        self.assertEqual(status, 200)
        status, thread = self.get("topic", made["id"])
        self.assertEqual([(p["parent"], p["text"]) for p in thread["posts"][1:]], [(root["id"], "welcome")])
        self.assertTrue(thread["can_reply"])

    def test_read_only_section_refuses_players(self):
        self.general.write = "authors"
        self.general.save()
        status, data = self.post("new_topic", {"section": self.general.pk, "title": "x", "text": "y"})
        self.assertEqual(status, 403)
        self.assertEqual(self.get("section", self.general.pk)[1]["can_write"], False)

    def test_hidden_post_has_no_text_and_hidden_topic_is_gone(self):
        topic = logic.start_topic(self.general, self.ivan, "T", "secret text", set())
        reply = logic.reply(topic, self.ivan, "spam", set())
        logic.hide_post(reply, "spam")
        status, thread = self.get("topic", topic.pk)
        self.assertEqual([(p["hidden"], p["text"]) for p in thread["posts"][1:]], [(True, "")])
        logic.hide_post(topic.posts.get(root=True))
        self.assertEqual(self.get("topic", topic.pk)[0], 404)

    def test_guest_reads_but_cannot_write(self):
        null = Machine.objects.create(name="Null", hostname="aether-null")
        make_app(null, label="forum", icon="chat", path="/apps/forum/")
        self.space.machines.add(null)
        topic = logic.author_topic(self.general, "SYSOP", "Rules", "be kind")
        self.client.logout()
        session = self.client.session
        session["guest"] = True
        session.save()
        status, thread = self.get("topic", topic.pk)
        self.assertEqual((status, thread["can_reply"]), (200, False))
        status, data = self.post("new_topic", {"section": self.general.pk, "title": "x", "text": "y"})
        self.assertEqual(status, 403)


@override_settings(FORCE_SCRIPT_NAME=None)
class PlayerSectionViewsTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(self.main, label="forum", icon="chat", path="/apps/forum/")
        self.space = Space.objects.create(slug="net", title="Net")
        self.space.machines.add(self.main)
        self.general = Section.objects.create(space=self.space, title="General")
        self.ivan = get_user_model().objects.create_user("ivan")
        self.client.force_login(self.ivan)

    def post(self, name, body):
        response = self.client.post(reverse(f"forum:{name}"), data=json.dumps(body), content_type="application/json")
        return response.status_code, response.json()

    def get(self, name, *args):
        return self.client.get(reverse(f"forum:{name}", args=args)).json()

    def test_space_and_section_say_whether_the_player_can_create(self):
        self.assertTrue(self.get("space", "net")["can_create"])
        self.assertTrue(self.get("section", self.general.pk)["can_create"])
        self.space.create = "authors"
        self.space.save()
        self.assertFalse(self.get("space", "net")["can_create"])

    def test_create_a_section_and_moderate_it(self):
        status, made = self.post("new_section", {"space": "net", "parent": None, "title": "Ciphers", "about": "x"})
        self.assertEqual(status, 200)
        section = self.get("section", made["id"])
        self.assertEqual((section["can_moderate"], section["can_write"]), (True, True))
        status, topic = self.post("new_topic", {"section": made["id"], "title": "Hi", "text": "hello"})
        thread = self.get("topic", topic["id"])
        self.assertTrue(thread["can_moderate"])
        root = thread["posts"][0]
        self.post("new_post", {"topic": topic["id"], "parent": root["id"], "text": "reply"})
        reply = self.get("topic", topic["id"])["posts"][1]
        self.assertEqual(self.post("hide_post", {"post": reply["id"], "reason": "x"})[0], 200)
        hidden = self.get("topic", topic["id"])["posts"][1]
        self.assertEqual((hidden["hidden"], hidden["text"]), (True, "reply"))              # модератор видит, что скрыл
        self.post("restore_post", {"post": reply["id"]})
        self.assertEqual(self.post("topic_flags", {"topic": topic["id"], "locked": True})[0], 200)
        self.assertFalse(self.get("topic", topic["id"])["can_reply"])
        self.assertEqual(self.post("archive_section", {"section": made["id"]})[0], 200)
        self.assertEqual([n["title"] for n in self.get("space", "net")["tree"]], ["General"])

    def test_others_cannot_moderate_or_create_where_closed(self):
        author = logic.author_topic(self.general, "SYSOP", "Rules", "be kind")
        post = author.posts.get(root=True)
        self.assertEqual(self.post("hide_post", {"post": post.pk})[0], 403)
        self.assertEqual(self.post("topic_flags", {"topic": author.pk, "pinned": True})[0], 403)
        self.assertEqual(self.post("archive_section", {"section": self.general.pk})[0], 403)
        self.assertFalse(self.get("topic", author.pk)["can_moderate"])
        self.general.create = "authors"
        self.general.save()
        status, data = self.post("new_section", {"space": "net", "parent": self.general.pk, "title": "Sub"})
        self.assertEqual(status, 403)
        self.assertIn("авторы", data["error"])

    def test_hidden_text_is_not_sent_to_non_moderators(self):
        mine = logic.create_section(self.space, None, get_user_model().objects.create_user("owner"), "Mine", "", set())
        topic = logic.author_topic(mine, "SYSOP", "T", "t")
        reply = logic.author_post(topic, "SYSOP", "secret")
        logic.hide_post(reply, "x")
        self.assertEqual(self.get("topic", topic.pk)["posts"][1]["text"], "")
