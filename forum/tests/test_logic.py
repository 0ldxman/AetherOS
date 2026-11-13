"""Правила форума: видимость по условиям, режим записи, наследование, ответы, лимиты, модерация."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from forum import logic
from forum.models import Kind, Post, Section, Space, Topic
from machines.models import Machine


class ForumLogicTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(name="Core", hostname="aether-core")
        self.space = Space.objects.create(slug="net", title="Net")
        self.space.machines.add(self.machine)
        self.root = Section.objects.create(space=self.space, title="General")
        self.sub = Section.objects.create(space=self.space, parent=self.root, title="Ciphers")
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_space_is_listed_only_for_bound_machines_and_when_readable(self):
        other = Machine.objects.create(name="Null", hostname="aether-null")
        self.assertEqual(logic.spaces_for(self.machine, set()), [self.space])
        self.assertEqual(logic.spaces_for(other, set()), [])
        self.space.read_if = "mask"
        self.space.save()
        self.assertEqual(logic.spaces_for(self.machine, set()), [])
        self.assertEqual(logic.spaces_for(self.machine, {"mask"}), [self.space])

    def test_section_tree_hides_what_the_player_cannot_read(self):
        self.sub.read_if = "cipher"
        self.sub.save()
        tree = logic.sections_of(self.space, set())
        self.assertEqual([(n["section"].title, n["children"]) for n in tree], [("General", [])])
        tree = logic.sections_of(self.space, {"cipher"})
        self.assertEqual([c["section"].title for c in tree[0]["children"]], ["Ciphers"])

    def test_write_mode_is_inherited_and_authors_only_blocks_players(self):
        self.assertTrue(logic.can_write(self.sub, self.ivan, set()))
        self.root.write = "authors"
        self.root.save()
        self.assertEqual(logic.write_mode(self.sub), "authors")
        self.assertFalse(logic.can_write(self.sub, self.ivan, set()))
        self.sub.write = "players"
        self.sub.save()
        self.assertTrue(logic.can_write(self.sub, self.ivan, set()))
        self.assertFalse(logic.can_write(self.sub, None, set()))

    def test_write_condition_and_archive(self):
        self.space.write_if = "pass"
        self.space.save()
        self.assertFalse(logic.can_write(self.root, self.ivan, set()))
        self.assertTrue(logic.can_write(self.root, self.ivan, {"pass"}))
        self.root.archived = True
        self.root.save()
        self.assertFalse(logic.can_write(self.root, self.ivan, {"pass"}))

    def test_topic_and_replies_with_signature_and_bump(self):
        topic = logic.start_topic(self.root, self.ivan, "Hello", "first", set())
        self.assertEqual((topic.kind, topic.name), (Kind.PLAYER, "IVAN"))
        first = topic.posts.get(root=True)
        reply = logic.reply(topic, self.ivan, "second", set())
        self.assertEqual(reply.parent, first)
        child = logic.reply(topic, self.ivan, "third", set(), parent=reply)
        self.assertEqual(child.parent, reply)
        listed = list(logic.topics_in(self.root))
        self.assertEqual([(t.pk, t.replies) for t in listed], [(topic.pk, 2)])
        self.assertGreaterEqual(Topic.objects.get(pk=topic.pk).bumped_at, topic.created_at)

    def test_reply_to_a_foreign_topic_post_and_to_a_deleted_one_is_refused(self):
        a = logic.start_topic(self.root, self.ivan, "A", "a", set())
        b = logic.start_topic(self.root, self.ivan, "B", "b", set())
        with self.assertRaises(logic.ForumError):
            logic.reply(a, self.ivan, "x", set(), parent=b.posts.get(root=True))
        post = logic.reply(a, self.ivan, "x", set())
        logic.hide_post(post, "spam")
        with self.assertRaises(logic.ForumError):
            logic.reply(a, self.ivan, "y", set(), parent=Post.objects.get(pk=post.pk))

    def test_depth_is_capped(self):
        topic = logic.start_topic(self.root, self.ivan, "Deep", "root", set())
        post = topic.posts.get(root=True)
        for n in range(logic.MAX_DEPTH + 3):
            post = logic.author_post(topic, "AUTHOR", f"level {n}", parent=post)
        depth, walk = 0, post
        while walk.parent_id is not None:
            depth, walk = depth + 1, walk.parent
        self.assertLessEqual(depth, logic.MAX_DEPTH)

    def test_locked_topic_text_limits_and_rate(self):
        topic = logic.start_topic(self.root, self.ivan, "T", "t", set())
        logic.set_flags(topic, locked=True)
        topic.refresh_from_db()
        with self.assertRaises(logic.ForumError):
            logic.reply(topic, self.ivan, "late", set())
        with self.assertRaises(logic.ForumError):
            logic.start_topic(self.root, self.ivan, "", "text", set())
        with self.assertRaises(logic.ForumError):
            logic.start_topic(self.root, self.ivan, "T", "x" * (logic.TEXT_MAX + 1), set())
        sender = get_user_model().objects.create_user("spammer")
        for n in range(logic.RATE_COUNT):
            logic.start_topic(self.root, sender, f"T{n}", "t", set())
        with self.assertRaises(logic.ForumError):
            logic.start_topic(self.root, sender, "more", "t", set())

    def test_hiding_the_first_post_hides_the_topic_and_restoring_brings_it_back(self):
        topic = logic.start_topic(self.root, self.ivan, "T", "t", set())
        logic.hide_post(topic.posts.get(root=True), "off-topic")
        self.assertEqual(list(logic.topics_in(self.root)), [])
        logic.restore_post(topic.posts.get(root=True))
        self.assertEqual(len(logic.topics_in(self.root)), 1)

    def test_authors_write_as_characters_or_system_and_pinned_comes_first(self):
        old = logic.author_topic(self.root, "SYSOP", "Rules", "Be kind")
        fresh = logic.start_topic(self.root, self.ivan, "New", "n", set())
        logic.set_flags(old, pinned=True)
        self.assertEqual([t.title for t in logic.topics_in(self.root)], ["Rules", "New"])
        reading = logic.author_topic(self.root, "SENSOR-4", "Counter", "act: 2", kind=Kind.SYSTEM)
        self.assertEqual((reading.kind, reading.author), (Kind.SYSTEM, None))
        self.assertEqual(fresh.kind, Kind.PLAYER)
