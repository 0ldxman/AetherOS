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


class PlayerSectionsTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(name="Core", hostname="aether-core")
        self.space = Space.objects.create(slug="net", title="Net")
        self.space.machines.add(self.machine)
        self.root = Section.objects.create(space=self.space, title="General")
        self.ivan = get_user_model().objects.create_user("ivan")
        self.anna = get_user_model().objects.create_user("anna")

    def test_a_player_creates_a_section_and_becomes_its_moderator(self):
        mine = logic.create_section(self.space, None, self.ivan, "Ciphers", "all about ciphers", set())
        self.assertEqual((mine.created_by, mine.parent), (self.ivan, None))
        self.assertTrue(logic.moderates(mine, self.ivan))
        self.assertFalse(logic.moderates(mine, self.anna))
        self.assertFalse(logic.moderates(self.root, self.ivan))
        sub = logic.create_section(self.space, mine, self.anna, "Vigenere", "", set())
        self.assertTrue(logic.moderates(sub, self.ivan))          # создатель верхнего раздела модерирует и вложенные
        self.assertTrue(logic.moderates(sub, self.anna))

    def test_depth_limit_and_duplicate_titles(self):
        one = logic.create_section(self.space, None, self.ivan, "One", "", set())
        two = logic.create_section(self.space, one, self.ivan, "Two", "", set())
        self.assertIn("глубже", logic.create_problem(self.space, two, self.anna, set()))
        with self.assertRaises(logic.ForumError):
            logic.create_section(self.space, None, self.anna, "one", "", set())

    def test_per_player_limit_counts_only_live_sections(self):
        made = [logic.create_section(self.space, None, self.ivan, f"S{n}", "", set()) for n in range(logic.PLAYER_SECTIONS)]
        self.assertIn("не больше", logic.create_problem(self.space, None, self.ivan, set()))
        logic.mod_archive(made[0], self.ivan)
        self.assertEqual(logic.create_problem(self.space, None, self.ivan, set()), "")

    def test_authors_can_close_creation_by_mode_and_condition(self):
        self.space.create = "authors"
        self.space.save()
        self.assertIn("авторы", logic.create_problem(self.space, None, self.ivan, set()))
        self.space.create = "players"
        self.space.create_if = "member"
        self.space.save()
        self.assertEqual(logic.create_problem(self.space, None, self.ivan, set()), "пока недоступно")
        self.assertEqual(logic.create_problem(self.space, None, self.ivan, {"member"}), "")
        self.root.create = "authors"
        self.root.save()
        self.assertIn("авторы", logic.create_problem(self.space, self.root, self.ivan, {"member"}))

    def test_unreadable_or_archived_parent_and_guests(self):
        self.root.read_if = "secret"
        self.root.save()
        self.assertEqual(logic.create_problem(self.space, self.root, self.ivan, set()), "раздела нет")
        self.root.read_if = None
        self.root.archived = True
        self.root.save()
        self.assertIn("нельзя", logic.create_problem(self.space, self.root, self.ivan, set()))
        from django.contrib.auth.models import AnonymousUser

        self.assertIn("только игроки", logic.create_problem(self.space, None, AnonymousUser(), set()))

    def test_moderator_hides_pins_locks_and_archives_only_in_their_section(self):
        mine = logic.create_section(self.space, None, self.ivan, "Mine", "", set())
        topic = logic.start_topic(mine, self.anna, "Hi", "hello", set())
        reply = logic.reply(topic, self.anna, "spam", set())
        logic.mod_hide(reply, self.ivan, "spam")
        self.assertIsNotNone(Post.objects.get(pk=reply.pk).hidden_at)
        logic.mod_restore(reply, self.ivan)
        logic.mod_flags(topic, self.ivan, pinned=True, locked=True)
        topic.refresh_from_db()
        self.assertEqual((topic.pinned, topic.locked), (True, True))
        foreign = logic.author_topic(self.root, "SYSOP", "Rules", "x")
        with self.assertRaises(logic.ForumError):
            logic.mod_flags(foreign, self.ivan, pinned=True)
        with self.assertRaises(logic.ForumError):
            logic.mod_hide(foreign.posts.get(root=True), self.ivan)
        with self.assertRaises(logic.ForumError):
            logic.mod_archive(mine, self.anna)
        logic.mod_archive(mine, self.ivan)
        mine.refresh_from_db()
        self.assertTrue(mine.archived)


class UsefulTests(TestCase):
    def setUp(self):
        self.section = Section.objects.create(space=Space.objects.create(slug="net", title="Net"), title="General")
        self.ivan = get_user_model().objects.create_user("ivan")
        self.anna = get_user_model().objects.create_user("anna")

    def test_only_the_topic_starter_marks_replies(self):
        topic = logic.start_topic(self.section, self.ivan, "Q", "how?", set())
        answer = logic.reply(topic, self.anna, "like this", set())
        with self.assertRaises(logic.ForumError):
            logic.mark_useful(answer, self.anna)
        logic.mark_useful(answer, self.ivan)
        self.assertTrue(Post.objects.get(pk=answer.pk).useful)
        logic.mark_useful(answer, self.ivan, on=False)
        self.assertFalse(Post.objects.get(pk=answer.pk).useful)
        with self.assertRaises(logic.ForumError):
            logic.mark_useful(topic.posts.get(root=True), self.ivan)
        with self.assertRaises(logic.ForumError):
            logic.mark_useful(logic.reply(topic, self.ivan, "my own", set()), self.ivan)
        authored = logic.author_topic(self.section, "SYSOP", "Rules", "x")
        with self.assertRaises(logic.ForumError):
            logic.mark_useful(logic.reply(authored, self.anna, "ok", set()), self.ivan)
