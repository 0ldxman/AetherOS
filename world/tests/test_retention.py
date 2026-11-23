"""Чистка служебных таблиц: старые эффекты стола и журнал мира уходят, свежие и события игрока остаются."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine.models import Event, Push
from world import retention
from world.models import WorldEvent


class RetentionTests(TestCase):
    def test_sweep_removes_only_old_service_rows(self):
        user = get_user_model().objects.create_user("p")
        old = timezone.now() - timedelta(days=40)
        Push.objects.create(user=user, op="toast")
        stale = Push.objects.create(user=user, op="toast")
        Push.objects.filter(pk=stale.pk).update(created_at=old)
        WorldEvent.objects.create(kind="flag", text="свежее")
        gone = WorldEvent.objects.create(kind="flag", text="старое")
        WorldEvent.objects.filter(pk=gone.pk).update(at=old)
        event = Event.objects.create(name="key.got", user=user)
        Event.objects.filter(pk=event.pk).update(at=old)
        self.assertEqual(retention.sweep(), {"push": 1, "world_events": 1})
        self.assertEqual((Push.objects.count(), WorldEvent.objects.count(), Event.objects.count()), (1, 1, 1))
