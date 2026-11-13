"""Новое с прошлого визита: темы, ответы, свои сообщения, гость."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone

from forum import logic, reading
from forum.models import Reader, Section, Space


class ReadingTests(TestCase):
    def setUp(self):
        self.space = Space.objects.create(slug="net", title="Net")
        self.section = Section.objects.create(space=self.space, title="General")
        self.ivan = get_user_model().objects.create_user("ivan")
        self.anna = get_user_model().objects.create_user("anna")

    def summary(self, topic, user):
        return reading.summaries([topic], user)[topic.pk]

    def test_what_existed_before_the_first_visit_is_not_new(self):
        old = logic.author_topic(self.section, "SYSOP", "Rules", "**Be** kind")
        Reader.objects.filter(user=self.ivan).delete()
        reading.since(self.ivan)
        info = self.summary(old, self.ivan)
        self.assertEqual((info["unseen"], info["new"], info["excerpt"]), (False, 0, "Be kind"))

    def test_new_topic_then_seen_then_new_replies_but_not_own(self):
        Reader.objects.create(user=self.ivan, since=timezone.now() - timedelta(minutes=1))
        topic = logic.start_topic(self.section, self.anna, "Hi", "hello", set())
        self.assertTrue(self.summary(topic, self.ivan)["unseen"])
        reading.mark_seen(topic, self.ivan)
        self.assertFalse(self.summary(topic, self.ivan)["unseen"])
        logic.reply(topic, self.ivan, "me", set())
        reply = logic.reply(topic, self.anna, "anyone?", set())
        info = self.summary(topic, self.ivan)
        self.assertEqual((info["new"], info["replies"], info["last_name"]), (1, 2, logic.author_name(self.anna)))
        self.assertEqual(reading.new_posts(topic, self.ivan), {reply.pk})
        reading.mark_seen(topic, self.ivan)
        self.assertEqual(self.summary(topic, self.ivan)["new"], 0)

    def test_guest_sees_nothing_new_and_long_texts_are_cut(self):
        topic = logic.author_topic(self.section, "SYSOP", "Long", "x " * 200)
        info = self.summary(topic, AnonymousUser())
        self.assertEqual((info["new"], info["unseen"]), (0, False))
        self.assertLessEqual(len(info["excerpt"]), reading.EXCERPT)
        self.assertTrue(info["excerpt"].endswith("…"))

    def test_a_reply_of_mine_means_i_saw_what_came_before_it(self):
        Reader.objects.create(user=self.ivan, since=timezone.now() - timedelta(minutes=5))
        topic = logic.start_topic(self.section, self.ivan, "Hi", "hello", set())
        reading.mark_seen(topic, self.ivan)
        first = logic.reply(topic, self.anna, "one", set())
        logic.reply(topic, self.ivan, "answer", set(), parent=first)        # ответил, не открывая тему заново
        self.assertEqual(reading.new_posts(topic, self.ivan), set())
        self.assertEqual(self.summary(topic, self.ivan)["new"], 0)
        later = logic.reply(topic, self.anna, "two", set())
        self.assertEqual(reading.new_posts(topic, self.ivan), {later.pk})
