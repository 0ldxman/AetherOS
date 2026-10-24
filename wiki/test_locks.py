"""Блокировка записи и проверка версии при сохранении.

Запуск: python manage.py test wiki.test_locks
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix
from django.utils import timezone

from wiki import locks
from wiki.models import Document, DocumentLock


def make_users():
    User = get_user_model()
    return (
        User.objects.create_superuser("anna", password="pw"),
        User.objects.create_superuser("boris", password="pw"),
    )


class LockServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anna, cls.boris = make_users()
        cls.doc = Document.objects.create(title="Д")

    def test_free_document_is_taken(self):
        self.assertIsNone(locks.acquire(self.doc, self.anna))
        self.assertEqual(locks.holder(self.doc).user, self.anna)

    def test_own_lock_is_refreshed(self):
        locks.acquire(self.doc, self.anna)
        DocumentLock.objects.update(refreshed_at=timezone.now() - timedelta(seconds=60))
        self.assertIsNone(locks.acquire(self.doc, self.anna))
        self.assertLess(timezone.now() - DocumentLock.objects.get().refreshed_at, timedelta(seconds=5))

    def test_other_user_sees_the_holder(self):
        locks.acquire(self.doc, self.anna)
        other = locks.acquire(self.doc, self.boris)
        self.assertEqual(other.user, self.anna)

    def test_expired_lock_is_taken_over(self):
        locks.acquire(self.doc, self.anna)
        DocumentLock.objects.update(refreshed_at=timezone.now() - locks.LOCK_TTL - timedelta(seconds=1))
        self.assertIsNone(locks.holder(self.doc))
        self.assertIsNone(locks.acquire(self.doc, self.boris))
        self.assertEqual(locks.holder(self.doc).user, self.boris)

    def test_release_only_removes_own_lock(self):
        locks.acquire(self.doc, self.anna)
        locks.release(self.doc, self.boris)
        self.assertIsNotNone(locks.holder(self.doc))
        locks.release(self.doc, self.anna)
        self.assertIsNone(locks.holder(self.doc))


@override_settings(FORCE_SCRIPT_NAME=None)
class AdminLockTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.anna, self.boris = make_users()
        self.doc = Document.objects.create(title="Д", body="текст")

    def post(self, name):
        return self.client.post(reverse(f"admin:wiki_document_{name}", args=[self.doc.pk]))

    def test_heartbeat_reports_the_other_editor(self):
        self.client.force_login(self.anna)
        self.assertIsNone(self.post("lock").json()["holder"])
        self.client.force_login(self.boris)
        holder = self.post("lock").json()["holder"]
        self.assertEqual(holder["name"], "anna")

    def test_unlock_frees_the_document(self):
        self.client.force_login(self.anna)
        self.post("lock")
        self.post("unlock")
        self.client.force_login(self.boris)
        self.assertIsNone(self.post("lock").json()["holder"])

    def test_get_is_not_allowed(self):
        self.client.force_login(self.anna)
        response = self.client.get(reverse("admin:wiki_document_lock", args=[self.doc.pk]))
        self.assertEqual(response.status_code, 405)

    def test_change_form_embeds_lock_script(self):
        self.client.force_login(self.anna)
        response = self.client.get(reverse("admin:wiki_document_change", args=[self.doc.pk]))
        self.assertContains(response, "doc_lock.js")
        self.assertContains(response, 'name="base_version"')

    def test_list_shows_who_is_editing(self):
        self.client.force_login(self.anna)
        self.post("lock")
        response = self.client.get(reverse("admin:wiki_document_changelist"))
        self.assertContains(response, "anna")


@override_settings(FORCE_SCRIPT_NAME=None)
class OverwriteProtectionTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.anna, self.boris = make_users()
        self.doc = Document.objects.create(title="Д", body="v1", updated_by=self.anna)
        self.url = reverse("admin:wiki_document_change", args=[self.doc.pk])

    def form_for(self, user):
        """Открывает форму как пользователь и возвращает данные для отправки."""
        self.client.force_login(user)
        response = self.client.get(self.url)
        form = response.context["adminform"].form
        data = {
            name: (form.initial.get(name) if form.initial.get(name) is not None else "")
            for name in form.fields
        }
        data["namespace"] = ""
        data["visibility"] = "{}"
        data["access"] = "{}"
        return data

    def save(self, user, data):
        self.client.force_login(user)
        return self.client.post(self.url, data)

    def test_normal_save_goes_through(self):
        data = self.form_for(self.anna)
        data["body"] = "v2"
        self.assertEqual(self.save(self.anna, data).status_code, 302)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.body, "v2")

    def test_stale_form_is_rejected_and_keeps_the_text(self):
        annas = self.form_for(self.anna)
        borises = self.form_for(self.boris)
        borises["body"] = "от Бориса"
        self.assertEqual(self.save(self.boris, borises).status_code, 302)

        annas["body"] = "от Анны"
        response = self.save(self.anna, annas)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Запись изменена после того, как вы её открыли")
        self.assertContains(response, "от Анны")  # её текст остался в форме
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.body, "от Бориса")

    def test_second_submit_overwrites_knowingly(self):
        annas = self.form_for(self.anna)
        borises = self.form_for(self.boris)
        borises["body"] = "от Бориса"
        self.save(self.boris, borises)

        annas["body"] = "от Анны"
        response = self.save(self.anna, annas)
        retry = dict(annas, base_version=response.context["adminform"].form["base_version"].value())
        self.assertEqual(self.save(self.anna, retry).status_code, 302)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.body, "от Анны")
        # чужая версия осталась в истории
        self.assertIn("от Бориса", [r.body for r in self.doc.revisions.all()])
