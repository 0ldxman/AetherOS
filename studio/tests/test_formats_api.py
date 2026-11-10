from team.testing import full_role
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.models import FileEncoding, FileFormat, Item, ItemRevision


@override_settings(FORCE_SCRIPT_NAME=None)
class FormatsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)

    def call(self, method, path, body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"/studio/api{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def test_a_format_is_made_changed_and_listed_with_how_many_objects_use_it(self):
        body = {"name": "Memo", "title": "Служебка", "extension": ".memo", "kind": "text", "template": "MEMO\n{body}\n", "content": "text", "editable": True}
        status, made = self.call("post", "/file-formats", body)
        self.assertEqual((status, made["name"]), (200, "memo"))                      # имя приводится к строчным
        Item.objects.create(slug="m1", name="m1", format="memo", body="x")
        row = next(r for r in self.call("get", "/file-formats")[1] if r["name"] == "memo")
        self.assertEqual((row["used"], row["kind"], row["editable"]), (1, "text", True))
        status, saved = self.call("put", "/file-formats/memo", {**body, "name": "memo", "title": "Записка"})
        self.assertEqual((status, saved["title"]), (200, "Записка"))

    def test_the_same_checks_as_in_the_old_admin_name_the_wrong_field(self):
        status, answer = self.call("post", "/file-formats", {"name": "bad", "kind": "text", "template": "{nosuch}"})
        self.assertEqual(status, 400)
        self.assertIn("template", answer["fields"])
        status, answer = self.call("post", "/file-formats", {"name": "bad2", "kind": "signature", "magic": "zz"})
        self.assertIn("magic", answer["fields"])
        status, answer = self.call("post", "/file-formats", {"name": "bad3", "kind": "chunks", "magic": "89 50"})
        self.assertIn("parts", answer["fields"])                                       # блокам нужна хотя бы одна часть
        status, answer = self.call("post", "/file-formats", {"name": "bad4", "kind": "chunks", "magic": "89 50", "part_list": [{"name": "toolong", "source": "body"}]})
        self.assertIn("4 символа", answer["fields"]["parts"][0])

    def test_parts_are_replaced_in_order(self):
        body = {"name": "blk", "kind": "chunks", "magic": "89 50 4e 47", "part_list": [{"name": "IHDR", "source": "hex", "value": "00 01"}, {"name": "IDAT", "source": "body"}]}
        self.assertEqual(self.call("post", "/file-formats", body)[0], 200)
        body["part_list"] = [{"name": "IDAT", "source": "image"}]
        detail = self.call("put", "/file-formats/blk", body)[1]
        self.assertEqual([p["name"] for p in detail["part_list"]], ["IDAT"])

    def test_a_rename_moves_the_objects_and_a_used_format_cannot_be_deleted(self):
        FileFormat.objects.create(name="note", kind="text", template="{body}", content="text")
        item = Item.objects.create(slug="n1", name="n1", format="note", body="x")
        ItemRevision.objects.create(item=item, name="n1", format="note", body="x")
        status, _ = self.call("put", "/file-formats/note", {"name": "memo2", "kind": "text", "template": "{body}", "content": "text"})
        self.assertEqual(status, 200)
        self.assertEqual((Item.objects.get(pk=item.pk).format, set(ItemRevision.objects.values_list("format", flat=True))), ("memo2", {"memo2"}))
        status, answer = self.call("delete", "/file-formats/memo2")
        self.assertEqual(status, 400)
        self.assertIn("у объектов: 1", answer["fields"]["__all__"][0])
        item.delete()
        self.assertEqual(self.call("delete", "/file-formats/memo2")[0], 200)

    def test_an_alias_cannot_take_a_word_of_another_format(self):
        FileFormat.objects.update_or_create(name="jpg", defaults={"extension": ".jpg", "kind": "signature", "magic": "ff d8"})
        status, answer = self.call("post", "/file-formats", {"name": "jfif", "kind": "signature", "magic": "ff d8", "aliases": "jpg"})
        self.assertEqual(status, 400)
        self.assertIn("aliases", answer["fields"])

    def test_encodings_keep_their_name_and_check_the_parameter(self):
        status, made = self.call("post", "/file-encodings", {"name": "Shift", "kind": "rot", "param": "7"})
        self.assertEqual((status, made["name"]), (200, "shift"))
        self.assertEqual(self.call("post", "/file-encodings", {"name": "bad", "kind": "rot", "param": "x"})[0], 400)
        status, saved = self.call("put", "/file-encodings/shift", {"name": "other", "kind": "rot", "param": "9"})
        self.assertEqual((saved["name"], saved["param"]), ("shift", "9"))
        self.assertEqual(self.call("delete", "/file-encodings/shift")[0], 200)
        self.assertFalse(FileEncoding.objects.filter(name="shift").exists())
