from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from assets.services import asset_widget_kind, find_asset, resolve_viewer_type
from filesystem.models import Item


@override_settings(FORCE_SCRIPT_NAME=None)
class AssetObjectTests(TestCase):
    """Файл в хранилище это содержимое объекта: таблицы ассетов нет, адрес и слаг у самого объекта."""

    @classmethod
    def setUpTestData(cls):
        cls.photo = Item.objects.create(slug="harbor-photo", name="Порт", file_id="1", file_name="harbor.png", file_type="image/png", file_size=5)
        cls.closed = Item.objects.create(slug="gate-photo", name="Закрытое", file_id="2", file_name="gate.png", file_type="image/png", access="badge")
        cls.text = Item.objects.create(slug="no-file", name="Текст", body="hello")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def test_a_reference_finds_the_object_by_slug_or_public_id_and_only_with_a_file(self):
        self.assertEqual(find_asset("harbor-photo").item, self.photo)
        self.assertEqual(find_asset(f"asset:{self.photo.public_id}").item, self.photo)
        self.assertEqual(find_asset("harbor-photo").filename, "harbor.png")
        self.assertIsNone(find_asset("no-file"))
        self.assertIsNone(find_asset("ghost"))

    def test_the_kind_comes_from_the_type_and_the_name_of_the_file(self):
        self.assertEqual(asset_widget_kind(self.photo), "image")
        self.assertEqual(resolve_viewer_type("a.pdf", "application/pdf"), "PDF")
        self.assertEqual(resolve_viewer_type("a.log", "application/octet-stream"), "TEXT")
        self.assertEqual(asset_widget_kind(Item(file_id="3")), "file")                       # сведений о файле ещё нет

    def test_a_chosen_view_beats_the_type_of_the_file(self):
        odd = Item.objects.create(slug="odd", name="odd", file_id="9", file_name="dump.dat", file_type="application/octet-stream", file_view="text")
        self.assertEqual(asset_widget_kind(odd), "file")
        self.assertEqual(resolve_viewer_type("dump.dat", "application/octet-stream"), "RAW")
        from assets.services import asset_viewer_type
        self.assertEqual(asset_viewer_type(odd), "TEXT")
        pic = Item.objects.create(slug="pic-as-file", name="p", file_id="8", file_name="p.png", file_type="image/png", file_view="raw")
        self.assertEqual(asset_widget_kind(pic), "file")
        self.assertEqual(self.client.get(f"/view/{odd.public_id}/").status_code, 200)

    def test_the_viewer_opens_by_the_public_id(self):
        page = self.client.get(f"/view/{self.photo.public_id}/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.client.get(f"/view/{self.text.public_id}/").status_code, 404)       # у объекта нет файла

    def test_the_condition_of_the_object_closes_the_direct_link_too(self):
        url = f"/view/{self.closed.public_id}/"
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(url + "content/").status_code, 403)
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True))
        self.assertEqual(self.client.get(url).status_code, 200)                                    # сотрудник видит всё
