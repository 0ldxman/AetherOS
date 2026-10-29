"""API объектов в студии: библиотека с фильтрами, где объект лежит и кто на него ссылается, своя копия для места, удаление,
история с восстановлением.

Запуск: python manage.py test studio.tests.test_items
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
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


@override_settings(FORCE_SCRIPT_NAME=None)
class ProtectionApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from assets.models import Asset
        from mail.models import Message
        from map.models import MapScene

        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        FileFormat.objects.update_or_create(name="txt", defaults={"extension": ".txt", "kind": "text", "content": "text"})
        FileFormat.objects.update_or_create(name="png", defaults={"extension": ".png", "kind": "signature", "content": "asset"})
        FileFormat.objects.update_or_create(name="key", defaults={"extension": ".key", "kind": "text", "content": "text"})
        cls.door = Item.objects.create(slug="door", name="door", format="txt", body="код двери 4471")
        cls.card = Item.objects.create(slug="cardkey", name="cardkey", format="key")
        cls.alarm = Item.objects.create(slug="alarm", name="alarm", format="key")
        cls.asset = Asset.objects.create(name="Фото порта", file_id="1", size=11)
        cls.scene = MapScene.objects.create(slug="harbor", title="Порт")
        cls.message = Message.objects.create(subject="Груз", sender="ops@aether-core", recipients="*", sent_at=timezone.now())

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    call = ItemsApiTests.call

    def test_the_preview_names_bad_layers_with_their_lines_and_shows_the_bytes_both_ways(self):
        answer = self.call("post", f"/items/{self.door.pk}/protection/preview", {"state": "> encrypted hunter2", "access": "cardkey and not alarm"})[1]
        self.assertEqual(answer["problems"], [])
        self.assertEqual([layer["name"] for layer in answer["layers"]], ["encrypted"])
        self.assertEqual(answer["keys"], ["alarm", "cardkey"])
        self.assertTrue(answer["plain"]["rows"])
        self.assertNotEqual(answer["plain"]["rows"][0]["hex"], answer["layered"]["rows"][0]["hex"])         # слой меняет байты
        self.assertGreater(answer["plain"]["printable"], answer["layered"]["printable"])                      # без слоя читается текст

        bad = self.call("post", f"/items/{self.door.pk}/protection/preview", {"state": "> encrypted hunter2\n> nosuchlayer", "access": "a and ("})[1]
        self.assertEqual([p["line"] for p in bad["problems"]], [2])
        self.assertTrue(bad["access_error"])
        self.assertIsNone(bad["layered"])

    def test_the_protection_is_saved_with_a_version_and_a_key_that_is_not_in_the_registry_is_named(self):
        data = self.call("get", f"/items/{self.door.pk}/protection")[1]
        status, saved = self.call("put", f"/items/{self.door.pk}/protection", {**data, "access": "cardkey", "state": "> encrypted pw"})
        self.assertEqual((status, saved["access"], saved["state"]), (200, "cardkey", "> encrypted pw"))
        self.assertEqual(Item.objects.get(pk=self.door.pk).access, "cardkey")        # одиночный ключ secure.access хранит строкой
        status, conflict = self.call("put", f"/items/{self.door.pk}/protection", {**data, "access": ""})
        self.assertEqual(status, 409)
        status, answer = self.call("put", f"/items/{self.door.pk}/protection", {**saved, "access": "a and ("})
        self.assertEqual((status, "access" in answer["fields"]), (400, True))
        unknown = self.call("post", f"/items/{self.door.pk}/protection/preview", {"access": "ghost"})[1]
        self.assertEqual(unknown["unknown_keys"], ["ghost"])

    def test_keys_and_signatures_are_taken_from_the_registry_and_a_key_shows_where_it_is_required(self):
        status, data = self.call("put", f"/items/{self.door.pk}/keys", {
            "embedded": ["cardkey"], "signatures": [{"slug": "alarm", "valid": False, "date": "2041-03-12"}],
        })
        self.assertEqual(status, 200, data)
        self.assertEqual([k["slug"] for k in data["embedded"]], ["cardkey"])
        self.assertEqual((data["signatures"][0]["slug"], data["signatures"][0]["valid"]), ("alarm", False))
        self.assertEqual(self.call("put", f"/items/{self.door.pk}/keys", {"embedded": ["ghost"]})[0], 400)
        self.assertEqual(self.call("put", f"/items/{self.door.pk}/keys", {})[1]["embedded"], [])           # пустой список убирает

        self.call("put", f"/items/{self.door.pk}/protection", {"access": "cardkey", "state": "", "version": Item.objects.get(pk=self.door.pk).updated_at.isoformat()})
        keyed = self.call("get", f"/items/{self.card.pk}/keys")[1]
        self.assertTrue(keyed["is_key"])
        self.assertIn("door", " ".join(u["label"] for u in keyed["required_by"]))

    def test_the_content_comes_from_an_asset_a_scene_a_message_or_a_link_and_text_is_not_wiped_silently(self):
        picture = Item.objects.create(slug="pic", name="pic", format="png")
        self.assertEqual([r["label"] for r in self.call("get", "/items/pick/assets?q=порта")[1]], ["Фото порта"])
        self.assertEqual([r["sub"] for r in self.call("get", "/items/pick/scenes")[1]], ["harbor"])
        self.assertEqual(self.call("get", "/items/pick/messages?q=Груз")[1][0]["sub"], "ops@aether-core")
        data = self.call("put", f"/items/{picture.pk}/content", {"kind": "asset", "asset": self.asset.pk})[1]
        self.assertEqual((data["kind"], data["asset"]["label"]), ("asset", "Фото порта"))
        self.assertEqual(self.call("put", f"/items/{picture.pk}/content", {"kind": "scene", "scene": self.scene.pk})[0], 400)    # png: сцена не подходит
        self.assertEqual(self.call("put", f"/items/{picture.pk}/content", {"kind": "text"})[0], 400)      # png обязан иметь ассет
        status, answer = self.call("put", f"/items/{self.door.pk}/content", {"kind": "link", "url": "https://example.org"})
        self.assertEqual(status, 400)                                                                   # у объекта есть текст
        self.assertIn("очистите", answer["fields"]["__all__"][0])
