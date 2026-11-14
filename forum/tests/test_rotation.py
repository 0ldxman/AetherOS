"""Ротация тем по игровому времени, тома, сжатие архива, действие мира forum и хроника."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from characters.models import Character
from forum import chronicle, logic, rotation
from forum.models import Kind, Post, Section, Space, Topic
from machines.models import TimeAnchor
from machines.world import chrono
from world import state
from world.models import WorldEvent, WorldMoment, WorldTrigger


def ago(days):
    return timezone.now() - timedelta(days=days)


class RotationTests(TestCase):
    def setUp(self):
        TimeAnchor.objects.create(real_at=ago(400), game_at=ago(400), rate=1)       # игровое время идёт как реальное
        chrono.forget()
        self.space = Space.objects.create(slug="net", title="Net")
        self.board = Section.objects.create(space=self.space, title="General")
        self.ivan = get_user_model().objects.create_user("ivan")

    def topic(self, **fields):
        found = logic._create_topic(self.board, self.ivan, "Signal", "first", Kind.PLAYER, "IVAN")
        Topic.objects.filter(pk=found.pk).update(**fields)
        found.refresh_from_db()
        return found

    def test_settings_inherit_from_space_and_sections(self):
        self.space.rotation = {"idle_days": 30}
        self.space.save()
        sub = Section.objects.create(space=self.space, parent=self.board, title="Sub", rotation={"grace_days": 1})
        rules = rotation.settings_for(sub)
        self.assertEqual((rules["idle_days"], rules["grace_days"], rules["archive_days"]), (30, 1, 7))

    def test_clean_rejects_unknown_keys_and_bad_numbers(self):
        self.assertEqual(rotation.clean({"idle_days": "5", "grace_days": None}), {"idle_days": 5})
        with self.assertRaises(rotation.RotationError):
            rotation.clean({"nope": 1})
        with self.assertRaises(rotation.RotationError):
            rotation.clean({"idle_days": -1})

    def test_idle_topic_is_warned_then_closed_and_a_post_cancels_the_warning(self):
        found = self.topic(bumped_at=ago(15))
        rotation.tick(force=True)
        found.refresh_from_db()
        self.assertIsNotNone(found.warned_at)
        self.assertFalse(found.locked)
        self.assertTrue(found.posts.filter(kind=Kind.SYSTEM, text__contains="will be closed").exists())
        logic.reply(found, self.ivan, "still here", set())
        found.refresh_from_db()
        self.assertIsNone(found.warned_at)

        Topic.objects.filter(pk=found.pk).update(bumped_at=ago(15), warned_at=ago(4))
        rotation.tick(force=True)
        found.refresh_from_db()
        self.assertTrue(found.locked)
        self.assertEqual(found.closed_reason, "idle")

    def test_warning_post_does_not_bump_the_topic(self):
        found = self.topic(bumped_at=ago(15))
        rotation.tick(force=True)
        found.refresh_from_db()
        self.assertLess(found.bumped_at, ago(14))

    def test_pinned_and_system_topics_never_close_for_inactivity(self):
        pinned = self.topic(bumped_at=ago(40), pinned=True)
        system = logic.author_topic(self.board, "SYS", "Log", "start", Kind.SYSTEM)
        Topic.objects.filter(pk=system.pk).update(bumped_at=ago(40))
        rotation.tick(force=True)
        for item in (pinned, system):
            item.refresh_from_db()
            self.assertIsNone(item.warned_at)
            self.assertFalse(item.locked)

    def test_closed_topic_goes_to_archive_and_leaves_the_list(self):
        found = self.topic()
        logic.set_flags(found, locked=True)
        found.refresh_from_db()
        self.assertEqual(found.closed_reason, "manual")
        Topic.objects.filter(pk=found.pk).update(closed_at=ago(8))
        rotation.tick(force=True)
        found.refresh_from_db()
        self.assertIsNotNone(found.archived_at)
        self.assertEqual(list(logic.topics_in(self.board)), [])
        self.assertEqual(list(logic.topics_in(self.board, archive=True)), [found])
        logic.set_flags(found, locked=False)
        found.refresh_from_db()
        self.assertIsNone(found.archived_at)

    def test_compression_is_off_by_default_and_works_when_set(self):
        found = self.topic(locked=True, closed_at=ago(30), archived_at=ago(20))
        rotation.tick(force=True)
        found.refresh_from_db()
        self.assertFalse(found.compressed)
        self.space.rotation = {"compress_days": 10}
        self.space.save()
        rotation.tick(force=True)
        found.refresh_from_db()
        self.assertTrue(found.compressed)

    def test_frozen_time_never_rotates(self):
        TimeAnchor.objects.all().delete()
        chrono.forget()
        found = self.topic(bumped_at=ago(100))
        rotation.tick(force=True)
        found.refresh_from_db()
        self.assertIsNone(found.warned_at)

    def test_full_topic_continues_in_the_next_volume(self):
        self.space.rotation = {"volume_posts": 3}
        self.space.save()
        found = self.topic()
        logic.reply(found, self.ivan, "two", set())
        logic.reply(found, self.ivan, "three", set())
        rotation.tick(force=True)
        found.refresh_from_db()
        self.assertTrue(found.locked)
        self.assertEqual((found.closed_reason, found.volume), ("volume", 1))
        fresh = found.next
        self.assertEqual((fresh.title, fresh.volume, fresh.author), ("Signal", 2, self.ivan))


class WorldForumActionTests(TestCase):
    def setUp(self):
        self.space = Space.objects.create(slug="net", title="Net")
        self.board = Section.objects.create(space=self.space, title="Log", write="authors")

    def test_new_topic_from_the_system(self):
        state.run_action({"do": "forum", "section": self.board.pk, "title": "Alert", "text": "core at {world_core}"}, "test")
        topic = Topic.objects.get()
        self.assertEqual((topic.kind, topic.name), (Kind.SYSTEM, "SYS"))
        self.assertEqual(topic.posts.get().text, "core at {world_core}")      # неизвестная подстановка остаётся как есть

    def test_append_reuses_the_open_topic_and_rolls_volumes(self):
        self.space.rotation = {"volume_posts": 2}
        self.space.save()
        action = {"do": "forum", "section": self.board.pk, "mode": "append", "title": "World log", "text": "tick"}
        for _ in range(3):
            state.run_action(action, "test")
        topics = list(Topic.objects.order_by("pk"))
        self.assertEqual(len(topics), 2)
        self.assertTrue(topics[0].locked)
        self.assertEqual(topics[1].prev, topics[0])
        self.assertEqual(topics[1].posts.filter(text="tick").count(), 1)

    def test_character_signs_the_post(self):
        Character.objects.create(code="MAR", name="Mara", callsign="MARA")
        state.run_action({"do": "forum", "section": self.board.pk, "title": "Hi", "text": "hello", "character": "mar"}, "test")
        self.assertEqual(Topic.objects.get().character.code, "MAR")

    def test_problems_are_logged_and_checked(self):
        state.run_action({"do": "forum", "section": 999, "title": "x", "text": "y"}, "test")
        self.assertTrue(WorldEvent.objects.filter(text__contains="нет раздела форума").exists())
        self.assertTrue(state.check_actions([{"do": "forum", "section": self.board.pk, "title": "", "text": "y"}]))
        self.assertFalse(state.check_actions([{"do": "forum", "section": self.board.pk, "title": "t", "text": "y"}]))


class ChronicleTests(TestCase):
    def test_chronicle_section_and_trigger_per_moment(self):
        space = Space.objects.create(slug="net", title="Net")
        WorldMoment.objects.create(name="uplink", title="BOREAS UPLINK", schedule="daily 21:00")
        section, made = chronicle.create(space)
        self.assertEqual((section.write, made), ("authors", 1))
        trigger = WorldTrigger.objects.get(name="chronicle-uplink")
        self.assertTrue(trigger.repeat)
        state.fire(trigger)
        post = Post.objects.get(topic__section=section)
        self.assertIn("BOREAS UPLINK started", post.text)
        self.assertEqual(chronicle.create(space)[1], 0)                 # повторно триггеры не плодятся
