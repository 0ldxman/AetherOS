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

    def test_the_library_filters_by_markup_volume_and_folder_and_sorts(self):
        FileFormat.objects.update_or_create(name="doc", defaults={"extension": ".doc", "kind": "text", "content": "text", "markup": True})
        article = Item.objects.create(slug="article", name="article", format="doc", body="# Статья")
        Placement.objects.create(volume=self.home, name="article.doc", item=article)
        self.assertEqual(self.names("?only=markup"), ["article"])
        self.assertEqual(self.names(f"?volume={self.harbor.pk}"), ["report"])
        self.assertEqual(self.names(f"?volume={self.home.pk}"), ["article", "report"])
        self.assertEqual(self.names("?path=ports"), ["report"])
        self.assertEqual(self.names(f"?volume={self.home.pk}&path=ports"), [])
        rows = self.call("get", "/items?sort=name")[1]
        self.assertEqual([r["name"] for r in rows], sorted(r["name"] for r in rows))
        rows = self.call("get", "/items?sort=-name")[1]
        self.assertEqual([r["name"] for r in rows], sorted((r["name"] for r in rows), reverse=True))
        report = next(r for r in self.call("get", "/items")[1] if r["name"] == "report")
        self.assertEqual(sorted(report["where"]), ["harbor:/ports/report.txt", "home:/copy.txt"])

    def test_a_place_can_have_its_own_condition_and_layers(self):
        url = f"/items/{self.report.pk}/placements/{self.first.pk}/protection"
        self.assertEqual(self.call("get", url)[1], {"access_mode": "inherit", "access": "", "state_mode": "inherit", "state": ""})
        body = {"access_mode": "replace", "access": "a and not b", "state_mode": "replace", "state": "> corrupted"}
        status, saved = self.call("put", url, body)
        self.assertEqual((status, saved), (200, body))
        row = next(p for p in self.call("get", f"/items/{self.report.pk}/where")[1]["placements"] if p["placement"] == self.first.pk)
        self.assertEqual((row["own_access"], row["own_state"]), (True, True))
        status, error = self.call("put", url, body | {"access": "a and"})
        self.assertEqual(status, 400)
        self.assertIn("access", error["fields"])
        self.assertEqual(self.call("put", f"/items/{self.pack.pk}/placements/{self.first.pk}/protection", body)[0], 404)   # место чужого объекта

    def test_where_lists_places_archives_and_holders(self):
        data = self.call("get", f"/items/{self.report.pk}/where")[1]
        self.assertEqual(sorted(p["path"] for p in data["placements"]), ["copy.txt", "ports/report.txt"])
        placed = next(p for p in data["placements"] if p["path"] == "ports/report.txt")
        self.assertEqual((placed["mode"], placed["owner"], placed["volume_name"]), ("640", "ivan", "Harbor"))
        self.assertEqual(data["archives"], [{"archive": self.pack.pk, "name": "pack", "path": "docs/report.txt"}])
        self.assertEqual([h["kind"] for h in data["holders"]], ["архив"])
        members = self.call("get", f"/items/{self.pack.pk}/where")[1]["members"]
        self.assertEqual([m["path"] for m in members], ["docs/report.txt"])

    def test_an_item_is_created_alone_or_into_a_volume_and_a_taken_slug_is_refused(self):
        status, data = self.call("post", "/items", {"name": "fresh.txt"})
        self.assertEqual(status, 200)
        self.assertEqual(Item.objects.get(pk=data["id"]).placements.count(), 0)
        status, data = self.call("post", "/items", {"name": "other", "slug": "other-one", "volume": self.harbor.pk})
        self.assertEqual(Item.objects.get(pk=data["id"]).placements.get().volume, self.harbor)
        self.assertEqual(self.call("post", "/items", {"name": "again", "slug": "fresh"})[0], 400)

    def test_changing_the_format_renames_the_files_that_carried_the_old_extension(self):
        item = Item.objects.create(slug="memo", name="memo", format="txt")
        place = Placement.objects.create(volume=self.harbor, kind=Placement.Kind.ITEM, item=item, name="memo.txt")
        custom = Placement.objects.create(volume=self.harbor, kind=Placement.Kind.ITEM, item=item, name="mine.txt")
        status, data = self.call("put", f"/items/{item.pk}", {"name": "memo", "format": "doc", "version": item.updated_at.isoformat()})
        self.assertEqual(status, 200)
        place.refresh_from_db()
        custom.refresh_from_db()
        self.assertEqual((place.name, custom.name), ("memo" + FileFormat.objects.get(name="doc").extension, "mine.txt"))

    def test_the_preview_draws_only_the_asked_page(self):
        both = self.call("post", "/items/preview", {"format": "doc", "title": "t", "body": "text", "meta": "info"})[1]
        self.assertTrue(both["body"] and both["infobox"])
        only = self.call("post", "/items/preview", {"format": "doc", "title": "t", "body": "text", "meta": "info", "only": "infobox"})[1]
        self.assertEqual((only["body"], bool(only["infobox"])), ("", True))
        only = self.call("post", "/items/preview", {"format": "doc", "title": "t", "body": "text", "meta": "info", "only": "body"})[1]
        self.assertEqual((bool(only["body"]), only["infobox"]), (True, ""))

    def test_a_staff_member_opens_the_item_in_the_real_viewer_with_or_without_keys(self):
        FileFormat.objects.update_or_create(name="doc", defaults={"extension": ".doc", "kind": "text", "content": "text", "markup": True})
        item = Item.objects.create(slug="note", name="note", format="doc", body="Первая\nВторая")
        url = self.call("get", f"/items/{item.pk}")[1]["view_url"]
        self.assertIsNotNone(url)
        self.assertIsNone(self.call("get", f"/items/{self.lonely.pk}")[1]["view_url"])
        page = self.client.get(url + "&as=none")
        self.assertContains(page, "Вторая")
        self.assertEqual(self.client.get(url + "&as=all").status_code, 200)
        self.client.logout()
        self.client.force_login(get_user_model().objects.create_user("player", password="pw"))
        self.assertEqual(self.client.get(url).status_code, 404)

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
        from mail.models import Message
        from map.models import MapScene

        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        FileFormat.objects.update_or_create(name="txt", defaults={"extension": ".txt", "kind": "text", "content": "text"})
        FileFormat.objects.update_or_create(name="png", defaults={"extension": ".png", "kind": "signature", "content": "asset"})
        FileFormat.objects.update_or_create(name="key", defaults={"extension": ".key", "kind": "text", "content": "text"})
        cls.door = Item.objects.create(slug="door", name="door", format="txt", body="код двери 4471")
        cls.card = Item.objects.create(slug="cardkey", name="cardkey", format="key")
        cls.alarm = Item.objects.create(slug="alarm", name="alarm", format="key")
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
        self.assertEqual([r["sub"] for r in self.call("get", "/items/pick/scenes")[1]], ["harbor"])
        self.assertEqual(self.call("get", "/items/pick/messages?q=Груз")[1][0]["sub"], "ops@aether-core")
        from unittest import mock

        def found(item, client=None):
            item.file_name, item.file_type, item.file_size = "port.png", "image/png", 11

        with mock.patch.object(Item, "refresh_file", found):
            data = self.call("put", f"/items/{picture.pk}/content", {"kind": "asset", "file_id": "1"})[1]
        self.assertEqual((data["kind"], data["asset"]["label"], data["asset"]["kind"]), ("asset", "port.png", "image"))
        self.assertEqual(Item.objects.get(pk=picture.pk).file_size, 11)
        self.assertEqual(self.call("put", f"/items/{picture.pk}/content", {"kind": "scene", "scene": self.scene.pk})[0], 400)    # png: сцена не подходит
        self.assertEqual(self.call("put", f"/items/{picture.pk}/content", {"kind": "text"})[0], 400)      # png обязан иметь файл
        status, answer = self.call("put", f"/items/{self.door.pk}/content", {"kind": "link", "url": "https://example.org"})
        self.assertEqual(status, 400)                                                                   # у объекта есть текст
        self.assertIn("очистите", answer["fields"]["__all__"][0])


    def test_the_storage_is_browsed_inside_aether_only_and_a_missing_file_is_refused(self):
        from unittest import mock

        folder = {"path": "/AETHER", "items": [{"file_id": "7", "name": "a.png", "path": "/AETHER/a.png", "is_directory": False, "is_parent": False}]}
        with mock.patch("assets.services.NextcloudClient", create=True), mock.patch("assets.services.list_folder", return_value=folder):
            status, data = self.call("get", "/items/nextcloud")
        self.assertEqual((status, data["items"][0]["file_id"]), (200, "7"))
        self.assertEqual(self.call("get", "/items/nextcloud?path=etc")[0], 400)                      # вне AETHER
        picture = Item.objects.create(slug="pic2", name="pic2", format="png")
        with mock.patch.object(Item, "refresh_file", side_effect=ValueError("нет")):
            status, answer = self.call("put", f"/items/{picture.pk}/content", {"kind": "asset", "file_id": "404"})
        self.assertEqual(status, 400)
        self.assertIn("Nextcloud", answer["fields"]["__all__"][0])


@override_settings(FORCE_SCRIPT_NAME=None)
class TextFilesApiTests(TestCase):
    """Файлы со своим текстом в студии: создание, правка с защитой, предпросмотр и превращение в объект и обратно."""

    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        FileFormat.objects.update_or_create(name="txt", defaults={"extension": ".txt", "kind": "text", "template": "{body}", "content": "text_asset", "editable": True})
        cls.volume = Volume.objects.create(slug="harbor", name="Harbor")
        cls.etc = Placement.objects.create(volume=cls.volume, kind="folder", name="etc")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    call = ItemsApiTests.call

    def test_a_text_file_is_made_edited_and_previewed_without_an_object(self):
        status, made = self.call("post", f"/volumes/{self.volume.pk}/text-files", {"parent": self.etc.pk, "name": "motd.txt", "content": "Welcome"})
        self.assertEqual((status, made["path"], made["format"]), (200, "etc/motd.txt", "txt"))
        self.assertFalse(Item.objects.exists())
        base = f"/volumes/{self.volume.pk}/text-files/{made['id']}"
        preview = self.call("post", f"{base}/preview", {"content": "Welcome aboard", "state": "> encrypted pw"})[1]
        self.assertIn("Welcome", preview["plain"]["rows"][0]["ascii"])
        self.assertNotIn("Welcome", preview["layered"]["rows"][0]["ascii"])
        saved = self.call("put", base, {"content": "Welcome aboard", "access": "cardkey", "state": "> encrypted pw"})[1]
        self.assertEqual((saved["content"], saved["access"], saved["state"]), ("Welcome aboard", "cardkey", "> encrypted pw"))
        status, answer = self.call("put", base, {"content": "x", "state": "> nosuchlayer"})
        self.assertEqual((status, "state" in answer["fields"]), (400, True))
        tree = self.call("get", f"/volumes/{self.volume.pk}")[1]
        self.assertEqual(next(r for r in tree["rows"] if r["name"] == "motd.txt")["kind"], "file")

    def test_a_text_file_becomes_an_object_with_its_protection_and_back(self):
        placement = Placement.objects.create(volume=self.volume, parent=self.etc, kind="file", name="motd.txt", content="Welcome",
                                             state="> encrypted pw")
        made = self.call("post", f"/volumes/{self.volume.pk}/text-files/{placement.pk}/to-item")[1]
        item = Item.objects.get(pk=made["item"])
        self.assertEqual((item.name, item.format, item.body, item.state), ("motd", "txt", "Welcome", "> encrypted pw"))
        placement.refresh_from_db()
        self.assertEqual((placement.kind, placement.item, placement.content, placement.state), ("item", item, "", ""))

        self.assertEqual(self.call("get", f"/items/{item.pk}/text-blockers")[1], {"reasons": []})
        back = self.call("post", f"/items/{item.pk}/to-text", {"placement": placement.pk})[1]
        placement.refresh_from_db()
        self.assertEqual((back["placement"], placement.kind, placement.content, placement.state), (placement.pk, "file", "Welcome", "> encrypted pw"))
        self.assertFalse(Item.objects.filter(pk=item.pk).exists())

    def test_a_shared_object_does_not_become_a_text(self):
        item = Item.objects.create(slug="shared", name="shared", format="txt", body="x")
        first = Placement.objects.create(volume=self.volume, name="a.txt", item=item)
        Placement.objects.create(volume=self.volume, parent=self.etc, name="b.txt", item=item)
        self.assertIn("лежит в нескольких местах", self.call("get", f"/items/{item.pk}/text-blockers")[1]["reasons"])
        status, answer = self.call("post", f"/items/{item.pk}/to-text", {"placement": first.pk})
        self.assertEqual(status, 400)
        self.assertIn("нескольких местах", answer["detail"])
