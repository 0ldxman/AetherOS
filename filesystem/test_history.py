"""Версии и блокировка объектов: снимки по сохранению, список, сравнение, откат, защита от потери правок."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix
from django.utils import timezone

from filesystem import history
from filesystem.models import FileFormat, Item, ItemLock, ItemRevision


def text_item(slug="a", body="one", **fields):
    return Item.objects.create(slug=slug, name=fields.pop("name", slug), body=body, **fields)


class RecordingTests(TestCase):
    def test_every_content_change_adds_a_revision(self):
        item = text_item()
        self.assertEqual(item.revisions.count(), 1)
        item.body = "two"
        item.save()
        self.assertEqual(item.revisions.count(), 2)
        self.assertEqual(item.revisions.first().body, "two")

    def test_a_save_without_changes_adds_nothing(self):
        item = text_item()
        item.access = "key_a"                                         # права не входят в снимок
        item.save()
        self.assertEqual(item.revisions.count(), 1)

    def test_an_object_without_text_keeps_no_history(self):
        item = Item.objects.create(slug="blank", name="blank")
        item.size = 10
        item.save()
        self.assertEqual(item.revisions.count(), 0)

    def test_the_author_is_updated_by(self):
        user = get_user_model().objects.create_user("writer")
        self.assertEqual(text_item(updated_by=user).revisions.get().saved_by, user)

    def test_deleting_an_object_deletes_its_history(self):
        item = text_item()
        item.delete()
        self.assertEqual(ItemRevision.objects.count(), 0)


class DiffTests(TestCase):
    def test_rows_mark_added_and_removed_lines(self):
        rows = history.diff_rows("a\nb\nc", "a\nB\nc")
        self.assertEqual([(k, t) for k, t in rows if k in ("add", "del")], [("del", "b"), ("add", "B")])

    def test_compare_returns_only_changed_fields(self):
        old, new = Item(name="A", format="rec", body="x"), Item(name="B", format="rec", body="x")
        self.assertEqual(history.compare(old, new), {"name": ("A", "B")})


@override_settings(FORCE_SCRIPT_NAME=None)
class AdminHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("root", password="pw")
        cls.item = text_item("a", "first")
        cls.item.body = "second"
        cls.item.save()

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.admin)

    def url(self, name, *args):
        return reverse(f"admin:filesystem_item_{name}", args=args)

    def test_the_list_of_versions(self):
        page = self.client.get(self.url("revisions", self.item.pk))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.context["revisions"]), 2)
        self.assertEqual(page.context["revisions"][0].changed, ["Текст"])
        self.assertEqual(page.context["revisions"][1].changed, ["создана"])

    def test_the_detail_shows_the_change_against_the_previous_version(self):
        newest = self.item.revisions.first()
        page = self.client.get(self.url("revision", self.item.pk, newest.pk))
        self.assertEqual([k for k, _ in page.context["diff"]["body"] if k in ("add", "del")], ["del", "add"])
        first = self.item.revisions.last()
        self.assertIsNone(self.client.get(self.url("revision", self.item.pk, first.pk)).context["diff"])

    def test_a_version_can_be_compared_with_the_current_object(self):
        first = self.item.revisions.last()
        page = self.client.get(self.url("revision", self.item.pk, first.pk) + "?against=current")
        self.assertTrue(page.context["against_current"])
        self.assertIn("body", page.context["diff"])

    def test_the_version_of_another_object_is_404(self):
        other = text_item("b", "x")
        self.assertEqual(self.client.get(self.url("revision", self.item.pk, other.revisions.first().pk)).status_code, 404)

    def test_a_restore_makes_a_new_version_and_keeps_the_history(self):
        first = self.item.revisions.last()
        self.assertEqual(self.client.post(self.url("revision", self.item.pk, first.pk)).status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual((self.item.body, self.item.revisions.count()), ("first", 3))

    def test_the_change_form_links_to_the_history(self):
        page = self.client.get(self.url("change", self.item.pk))
        self.assertContains(page, self.url("revisions", self.item.pk))

    def test_a_reader_cannot_restore(self):
        reader = get_user_model().objects.create_user("reader", password="pw", is_staff=True)
        from django.contrib.auth.models import Permission

        reader.user_permissions.add(Permission.objects.get(codename="view_item"))
        self.client.force_login(reader)
        first = self.item.revisions.last()
        self.assertEqual(self.client.post(self.url("revision", self.item.pk, first.pk)).status_code, 403)
        self.assertEqual(self.client.get(self.url("revisions", self.item.pk)).status_code, 200)


class LockLogicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.item = text_item()
        cls.one = get_user_model().objects.create_user("one")
        cls.two = get_user_model().objects.create_user("two")

    def test_a_free_object_is_taken(self):
        self.assertIsNone(history.acquire(self.item, self.one))
        self.assertEqual(ItemLock.objects.get().user, self.one)

    def test_the_own_lock_is_refreshed(self):
        history.acquire(self.item, self.one)
        ItemLock.objects.update(refreshed_at=timezone.now() - timedelta(seconds=60))
        history.acquire(self.item, self.one)
        self.assertLess(timezone.now() - ItemLock.objects.get().refreshed_at, timedelta(seconds=5))

    def test_another_user_sees_the_holder(self):
        history.acquire(self.item, self.one)
        self.assertEqual(history.acquire(self.item, self.two).user, self.one)

    def test_an_expired_lock_is_taken_over(self):
        history.acquire(self.item, self.one)
        ItemLock.objects.update(refreshed_at=timezone.now() - history.LOCK_TTL - timedelta(seconds=1))
        self.assertIsNone(history.acquire(self.item, self.two))
        self.assertEqual(ItemLock.objects.get().user, self.two)

    def test_release_removes_only_the_own_lock(self):
        history.acquire(self.item, self.one)
        history.release(self.item, self.two)
        self.assertEqual(ItemLock.objects.count(), 1)
        history.release(self.item, self.one)
        self.assertEqual(ItemLock.objects.count(), 0)


@override_settings(FORCE_SCRIPT_NAME=None)
class AdminLockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("root", password="pw")
        cls.other = get_user_model().objects.create_superuser("other", password="pw")
        cls.item = text_item("a", "text")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.admin)

    def test_the_heartbeat_reports_the_other_editor(self):
        history.acquire(self.item, self.other)
        data = self.client.post(reverse("admin:filesystem_item_lock", args=[self.item.pk])).json()
        self.assertEqual(data["holder"]["name"], "other")

    def test_unlock_frees_the_object(self):
        self.client.post(reverse("admin:filesystem_item_lock", args=[self.item.pk]))
        self.client.post(reverse("admin:filesystem_item_unlock", args=[self.item.pk]))
        self.assertEqual(ItemLock.objects.count(), 0)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse("admin:filesystem_item_lock", args=[self.item.pk])).status_code, 405)

    def test_the_change_form_embeds_the_lock_script(self):
        page = self.client.get(reverse("admin:filesystem_item_change", args=[self.item.pk]))
        self.assertContains(page, "doc_lock.js")
        self.assertContains(page, 'id="wp-lock"')

    def test_the_list_shows_who_is_editing(self):
        history.acquire(self.item, self.other)
        self.assertContains(self.client.get(reverse("admin:filesystem_item_changelist")), "other")

    def post(self, **extra):
        data = {
            "slug": "a", "name": "a", "format": "", "body": "text", "url": "", "access": "{}", "state": "", "meta": "",
            "keys-TOTAL_FORMS": "0", "keys-INITIAL_FORMS": "0", "keys-MIN_NUM_FORMS": "0", "keys-MAX_NUM_FORMS": "1000",
            "signatures-TOTAL_FORMS": "0", "signatures-INITIAL_FORMS": "0", "signatures-MIN_NUM_FORMS": "0", "signatures-MAX_NUM_FORMS": "1000",
            "members-TOTAL_FORMS": "0", "members-INITIAL_FORMS": "0", "members-MIN_NUM_FORMS": "0", "members-MAX_NUM_FORMS": "1000",
            "base_version": self.item.updated_at.isoformat(),
        }
        data.update(extra)
        return self.client.post(reverse("admin:filesystem_item_change", args=[self.item.pk]), data)

    def test_a_normal_save_goes_through(self):
        self.assertEqual(self.post(body="edited").status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.body, "edited")

    def test_a_stale_form_is_rejected_and_keeps_the_text(self):
        Item.objects.filter(pk=self.item.pk).update(updated_at=timezone.now() + timedelta(minutes=1), body="someone else")
        response = self.post(body="my text")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Объект изменён после того")
        self.assertContains(response, "my text")
        self.item.refresh_from_db()
        self.assertEqual(self.item.body, "someone else")

    def test_a_second_submit_overwrites_knowingly(self):
        Item.objects.filter(pk=self.item.pk).update(updated_at=timezone.now() + timedelta(minutes=1), body="someone else")
        first = self.post(body="my text")
        version = first.context["adminform"].form.data["base_version"]
        self.assertEqual(self.post(body="my text", base_version=version).status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.body, "my text")
