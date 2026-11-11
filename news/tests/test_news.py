"""Новости: лента игрока, прочитанность, пульс стола, правка из Студии.

Запуск: python manage.py test news
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from news import feed
from news.models import Post
from team.testing import full_role


class FeedTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan", password="pw")
        now = timezone.now()
        self.old = Post.objects.create(title="Old", publish_at=now - timedelta(days=1))
        self.pinned = Post.objects.create(title="Pinned", publish_at=now - timedelta(days=2), pinned=True, important=True)
        Post.objects.create(title="Draft")
        Post.objects.create(title="Later", publish_at=now + timedelta(hours=1))

    def test_only_published_pinned_first_and_read_marks(self):
        self.assertEqual([p.title for p, _ in feed.feed(self.ivan)], ["Pinned", "Old"])
        self.assertEqual(feed.pulse(self.ivan)["unread"], 2)
        self.assertEqual(feed.mark_read(self.ivan, [self.old.pk, self.old.pk, 999]), 1)
        self.assertEqual(feed.pulse(self.ivan)["items"], [{"id": self.pinned.pk, "title": "Pinned", "important": True}])

    def test_drafts_and_scheduled_cannot_be_marked(self):
        draft = Post.objects.get(title="Draft")
        self.assertEqual(feed.mark_read(self.ivan, [draft.pk]), 0)
        self.assertEqual((draft.status, Post.objects.get(title="Later").status, self.old.status), ("draft", "scheduled", "published"))


@override_settings(FORCE_SCRIPT_NAME=None)
class StudioNewsTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.client.force_login(self.boss)

    def test_create_publish_and_delete(self):
        made = self.client.post("/studio/api/news", data=json.dumps({"title": " Hi ", "body": "text"}), content_type="application/json").json()
        self.assertEqual((made["title"], made["status"], made["author"]), ("Hi", "draft", "boss"))
        changed = self.client.put(f"/studio/api/news/{made['id']}", data=json.dumps({"title": "Hi", "publish_at": timezone.now().isoformat()}),
                                  content_type="application/json").json()
        self.assertEqual(changed["status"], "published")
        self.assertEqual(self.client.get("/studio/api/news").json()[0]["reads"], 0)
        self.assertEqual(self.client.delete(f"/studio/api/news/{made['id']}").status_code, 204)
