"""API объектов в студии: библиотека с фильтрами, где объект лежит и кто на него ссылается, своя копия для места, удаление,
история с восстановлением.

Запуск: python manage.py test studio.tests.test_items
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.models import FileFormat, Item, ItemMember, ItemRevision, Placement, Volume

API = "/studio/api"


@override_settings(FORCE_SCRIPT_NAME=None)
class ItemsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        FileFormat.objects.update_or_create(name="txt", defaults={"extension": ".txt", "kind": "text", "content": "text"})
        cls.harbor = Volume.objects.create(slug="harbor", name="Harbor")
        cls.home = Volume.objects.create(slug="home")
        cls.report = Item.objects.create(slug="report", name="report", format="txt", body="Груз ушёл", state="> encrypted pw")
        cls.lonely = Item.objects.create(slug="lonely", name="lonely", format="txt", body="никому не нужен")
        cls.pack = Item.objects.create(slug="pack", name="pack", format="zip")
        ItemMember.objects.create(archive=cls.pack, path="docs/report.txt", item=cls.report)
        cls.ports = Placement.objects.create(volume=cls.harbor, kind="folder", name="ports")
        cls.first = Placement.objects.create(volume=cls.harbor, parent=cls.ports, name="report.txt", item=cls.report, mode="640", owner="ivan")
        cls.second = Placement.objects.create(volume=cls.home, name="copy.txt", item=cls.report)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def call(self, method, path, body=None):
        response = getattr(self.client, method)(API + path, data=json.dumps(body) if body is not None else None, content_type="application/json")
        return response.status_code, (response.json() if response.content else None)

    def names(self, query=""):
        return sorted(row["name"] for row in self.call("get", f"/items{query}")[1])

    def test_the_library_filters(self):
        self.assertEqual(self.names("?only=orphans"), ["lonely", "pack"])   # ни в томе, ни в архиве
        self.assertEqual(self.names("?only=shared"), ["report"])
        self.assertEqual(self.names("?only=layers"), ["report"])
        self.assertEqual(self.names("?q=нужен"), ["lonely"])
        self.assertEqual(self.names("?kind=empty"), ["pack"])
        row = next(r for r in self.call("get", "/items")[1] if r["name"] == "report")
        self.assertEqual((row["places"], row["archives"], row["layers"]), (2, 1, True))

    def test_where_lists_places_archives_and_holders(self):
        data = self.call("get", f"/items/{self.report.pk}/where")[1]
        self.assertEqual(sorted(p["path"] for p in data["placements"]), ["copy.txt", "ports/report.txt"])
        placed = next(p for p in data["placements"] if p["path"] == "ports/report.txt")
        self.assertEqual((placed["mode"], placed["owner"], placed["volume_name"]), ("640", "ivan", "Harbor"))
        self.assertEqual(data["archives"], [{"archive": self.pack.pk, "name": "pack", "path": "docs/report.txt"}])
        self.assertEqual([h["kind"] for h in data["holders"]], ["архив"])
        members = self.call("get", f"/items/{self.pack.pk}/where")[1]["members"]
        self.assertEqual([m["path"] for m in members], ["docs/report.txt"])

    def test_an_item_is_put_in_one_more_place(self):
        data = self.call("post", f"/items/{self.lonely.pk}/placements", {"volume": self.harbor.pk, "parent": self.ports.pk})[1]
        self.assertEqual([p["path"] for p in data["placements"]], ["ports/lonely.txt"])

    def test_a_place_gets_its_own_copy_and_edits_do_not_cross(self):
        status, answer = self.call("post", f"/items/{self.report.pk}/detach", {"placement": self.second.pk})
        self.assertEqual(status, 200)
        copy = Item.objects.get(pk=answer["id"])
        self.second.refresh_from_db()
        self.assertEqual((self.second.item, copy.body, copy.state), (copy, "Груз ушёл", "> encrypted pw"))
        copy.body = "другое"
        copy.save()
        self.report.refresh_from_db()
        self.assertEqual(self.report.body, "Груз ушёл")

    def test_an_item_held_by_an_archive_is_not_deleted_and_a_free_one_goes_with_its_places(self):
        status, answer = self.call("delete", f"/items/{self.report.pk}")
        self.assertEqual(status, 400)
        self.assertIn("pack", answer["detail"])
        Placement.objects.create(volume=self.home, name="lonely.txt", item=self.lonely)
        self.assertEqual(self.call("delete", f"/items/{self.lonely.pk}"), (200, {"placements": 1}))
        self.assertFalse(Item.objects.filter(pk=self.lonely.pk).exists())

    def test_a_revision_shows_the_difference_and_is_restored(self):
        first = ItemRevision.objects.filter(item=self.report).first()
        self.report.body = "Груз ушёл\nна рассвете"
        self.report.save()
        data = self.call("get", f"/items/{self.report.pk}/revisions/{first.pk}")[1]
        self.assertIn("body", data["changes"])
        restored = self.call("post", f"/items/{self.report.pk}/revisions/{first.pk}/restore")[1]
        self.assertEqual((restored["body"], restored["updated_by"]), ("Груз ушёл", "boss"))
        self.assertEqual(ItemRevision.objects.filter(item=self.report).count(), 3)
