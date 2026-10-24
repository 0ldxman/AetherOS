"""История версий записей: снимки по сохранению, список, сравнение, откат.

Запуск: python manage.py test wiki.test_revisions
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from wiki.models import Document, DocumentRevision, Namespace
from wiki.revisions import compare, diff_rows


class RecordingTests(TestCase):
    def test_every_content_change_adds_a_revision(self):
        doc = Document.objects.create(title="A", body="one")
        self.assertEqual(doc.revisions.count(), 1)

        doc.body = "two"
        doc.save()
        self.assertEqual(doc.revisions.count(), 2)
        self.assertEqual(doc.revisions.first().body, "two")

    def test_save_without_changes_adds_nothing(self):
        doc = Document.objects.create(title="A", body="one")
        doc.access = "key_a"  # права не входят в снимок
        doc.save()
        self.assertEqual(doc.revisions.count(), 1)

    def test_author_is_updated_by(self):
        user = get_user_model().objects.create_user("writer")
        doc = Document.objects.create(title="A", updated_by=user)
        self.assertEqual(doc.revisions.get().saved_by, user)

    def test_deleting_document_deletes_history(self):
        doc = Document.objects.create(title="A")
        doc.delete()
        self.assertEqual(DocumentRevision.objects.count(), 0)


class DiffTests(TestCase):
    def test_rows_mark_added_and_removed_lines(self):
        rows = diff_rows("a\nb\nc", "a\nB\nc")
        kinds = [(k, t) for k, t in rows if k in ("add", "del")]
        self.assertEqual(kinds, [("del", "b"), ("add", "B")])

    def test_compare_returns_only_changed_fields(self):
        old = Document(title="A", type="doc", body="x", infobox="")
        new = Document(title="B", type="doc", body="x", infobox="")
        self.assertEqual(compare(old, new), {"title": ("A", "B")})


@override_settings(FORCE_SCRIPT_NAME=None)
class AdminRevisionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("root", password="pw")
        cls.doc = Document.objects.create(title="A", body="first")
        cls.doc.body = "second"
        cls.doc.save()
        cls.first, cls.second = sorted(cls.doc.revisions.all(), key=lambda r: r.pk)

    def setUp(self):
        # reverse() берёт префикс из потока, а не из настроек: в разработке там /proxy/8000
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.admin)

    def url(self, name, *args):
        return reverse(f"admin:wiki_document_{name}", args=args)

    def test_list(self):
        response = self.client.get(self.url("revisions", self.doc.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["revisions"]), 2)

    def test_detail_shows_change_against_previous(self):
        response = self.client.get(self.url("revision", self.doc.pk, self.second.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("body", response.context["diff"])

    def test_first_revision_has_no_previous(self):
        response = self.client.get(self.url("revision", self.doc.pk, self.first.pk))
        self.assertIsNone(response.context["diff"])

    def test_compare_with_current(self):
        response = self.client.get(
            self.url("revision", self.doc.pk, self.first.pk), {"against": "current"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["diff"]["body"])

    def test_revision_of_another_document_is_404(self):
        other = Document.objects.create(title="B")
        response = self.client.get(self.url("revision", self.doc.pk, other.revisions.get().pk))
        self.assertEqual(response.status_code, 404)

    def test_restore_creates_new_revision_and_keeps_history(self):
        response = self.client.post(self.url("revision", self.doc.pk, self.first.pk))
        self.assertRedirects(
            response, self.url("revisions", self.doc.pk), fetch_redirect_response=False
        )
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.body, "first")
        self.assertEqual(self.doc.updated_by, self.admin)
        self.assertEqual(self.doc.revisions.count(), 3)

    def test_restore_with_taken_title_reports_error(self):
        self.doc.title = "Renamed"
        self.doc.save()
        Document.objects.create(title="A")  # старое название теперь занято
        response = self.client.post(self.url("revision", self.doc.pk, self.first.pk), follow=True)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.title, "Renamed")
        self.assertIn("Не удалось восстановить", "".join(str(m) for m in response.context["messages"]))

    def test_change_form_links_to_history(self):
        response = self.client.get(reverse("admin:wiki_document_change", args=[self.doc.pk]))
        self.assertContains(response, self.url("revisions", self.doc.pk))


@override_settings(FORCE_SCRIPT_NAME=None)
class PreviewIssuesTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(get_user_model().objects.create_superuser("root", password="pw"))

    def test_preview_returns_lint_issues_per_field(self):
        import json

        response = self.client.post(
            reverse("admin:wiki_document_preview"),
            json.dumps({"body": "::box\nнет закрытия", "infobox": "ок", "type": "doc"}),
            content_type="application/json",
        )
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual([i["code"] for i in data["issues"]["body"]], ["unclosed-block"])
        self.assertEqual(data["issues"]["infobox"], [])


@override_settings(FORCE_SCRIPT_NAME=None)
class AssetSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from assets.models import Asset

        Asset.objects.create(
            name="City theme", slug="theme-01", file_id="a", filename="city.mp3",
            viewer_type=Asset.ViewerType.AUDIO,
        )
        Asset.objects.create(name="Map", file_id="b", filename="map.png", viewer_type=Asset.ViewerType.IMAGE)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(get_user_model().objects.create_superuser("root", password="pw"))
        self.url = reverse("admin:wiki_document_assets")

    def test_search_by_name_slug_or_filename(self):
        for query in ("city", "theme-01", "city.mp3"):
            items = self.client.get(self.url, {"q": query}).json()["items"]
            self.assertEqual([i["ref"] for i in items], ["theme-01"], query)

    def test_ref_falls_back_to_uuid_and_kind_is_the_widget_name(self):
        from assets.models import Asset

        items = {i["name"]: i for i in self.client.get(self.url).json()["items"]}
        self.assertEqual(items["City theme"]["kind"], "audio")
        self.assertEqual(items["Map"]["kind"], "image")
        self.assertEqual(items["Map"]["ref"], str(Asset.objects.get(name="Map").public_id))

    def test_requires_staff(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
