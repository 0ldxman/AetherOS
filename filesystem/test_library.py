"""Тома, объекты, размещения и слой игрока (docs/storage-spec.md)."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from assets.models import Asset
from filesystem.models import (
    MAX_DEPTH, FileFormat, Item, ItemKey, ItemSignature, PlayerFile, Placement, Volume, VolumeInstance,
)
from machines.models import Machine


def make_format(name, extension="", content="text_asset", **extra):
    """Формат реестра: миграции уже кладут часть форматов (txt, png...), поэтому существующий обновляется."""
    found, _ = FileFormat.objects.update_or_create(name=name, defaults={"extension": extension, "content": content, **extra})
    return found


class ItemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_format("txt", ".txt", "text_asset")
        make_format("png", ".png", "link_asset")
        make_format("mp3", ".mp3", "asset")
        make_format("key", ".key", "text")
        make_format("blank", ".dat", "none")
        cls.asset = Asset.objects.create(name="pic", file_id="1")

    def item(self, slug, **fields):
        fields.setdefault("name", slug)
        return Item(slug=slug, **fields)

    def test_default_filename_is_the_name_with_the_extension_of_the_format(self):
        self.assertEqual(self.item("a", name="Report", format="txt").default_filename, "Report.txt")
        self.assertEqual(self.item("b", name="passwd").default_filename, "passwd")

    def test_an_unknown_format_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self.item("a", format="nope").full_clean()
        self.assertIn("format", caught.exception.message_dict)

    def test_a_text_format_takes_a_body_or_an_asset_but_not_both(self):
        self.item("a", format="txt", body="hello").full_clean()
        self.item("b", format="txt", asset=self.asset).full_clean()
        self.item("c", format="txt").full_clean()                                      # пустой файл допустим
        with self.assertRaises(ValidationError):
            self.item("d", format="txt", body="hello", asset=self.asset).full_clean()

    def test_an_image_takes_a_link_or_an_asset_and_needs_one(self):
        self.item("a", format="png", url="https://example.com/a.png").full_clean()
        self.item("b", format="png", asset=self.asset).full_clean()
        with self.assertRaises(ValidationError):
            self.item("c", format="png").full_clean()
        with self.assertRaises(ValidationError):
            self.item("d", format="png", body="text").full_clean()

    def test_only_http_links_are_allowed(self):
        with self.assertRaises(ValidationError):
            self.item("a", format="png", url="javascript:alert(1)").full_clean()
        with self.assertRaises(ValidationError):
            self.item("b", format="png", url="file:///etc/passwd").full_clean()

    def test_an_asset_only_format_refuses_text_and_needs_the_asset(self):
        self.item("a", format="mp3", asset=self.asset).full_clean()
        with self.assertRaises(ValidationError):
            self.item("b", format="mp3").full_clean()
        with self.assertRaises(ValidationError):
            self.item("c", format="mp3", body="x", asset=self.asset).full_clean()

    def test_a_format_without_content_refuses_everything(self):
        self.item("a", format="blank", size=100).full_clean()
        with self.assertRaises(ValidationError):
            self.item("b", format="blank", body="x").full_clean()

    def test_names_cannot_hold_a_slash_a_colon_or_be_a_dot_name(self):
        for bad in ("a/b", "a:b", "a\\b", "..", " lead", ""):
            with self.assertRaises(ValidationError, msg=bad):
                self.item("x", name=bad).full_clean()
        self.item("x", name="Мой отчёт 2").full_clean()                              # пробелы и кириллица допустимы

    def test_an_embedded_key_must_be_a_key_object(self):
        thing = self.item("thing", format="txt")
        thing.save()
        key = self.item("alpha", format="key", body="k")
        key.save()
        ItemKey(item=thing, key=key).full_clean()
        with self.assertRaises(ValidationError):
            ItemKey(item=thing, key=thing).full_clean()                              # не ключ
        with self.assertRaises(ValidationError):
            ItemSignature(item=thing, key=thing).full_clean()
        ItemSignature(item=thing, key=key).full_clean()

    def test_a_placed_object_cannot_be_deleted(self):
        thing = Item.objects.create(slug="a", name="a", format="txt")
        volume = Volume.objects.create(slug="v")
        Placement.objects.create(volume=volume, kind="item", item=thing)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            thing.delete()


class VolumeTreeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_format("txt", ".txt", "text_asset")
        cls.volume = Volume.objects.create(slug="harbor")
        cls.other = Volume.objects.create(slug="other")
        cls.item = Item.objects.create(slug="report", name="Report", format="txt", body="x")

    def folder(self, name, parent=None, volume=None):
        return Placement.objects.create(volume=volume or self.volume, kind="folder", name=name, parent=parent)

    def test_a_volume_has_an_uuid_made_for_it_and_a_label_for_the_admin(self):
        self.assertTrue(self.volume.uuid)
        self.assertNotEqual(self.volume.uuid, self.other.uuid)

    def test_an_object_is_placed_under_its_own_name_with_the_extension(self):
        placed = Placement.objects.create(volume=self.volume, kind="item", item=self.item)
        self.assertEqual(placed.name, "Report.txt")

    def test_the_same_object_lies_in_two_volumes_and_may_have_a_different_name(self):
        Placement.objects.create(volume=self.volume, kind="item", item=self.item)
        again = Placement.objects.create(volume=self.other, kind="item", item=self.item, name=".hidden.txt")
        self.assertEqual(again.name, ".hidden.txt")
        self.assertEqual(self.item.placements.count(), 2)

    def test_the_path_runs_through_the_folders(self):
        etc = self.folder("etc")
        aether = self.folder("aether", etc)
        placed = Placement.objects.create(volume=self.volume, kind="item", item=self.item, parent=aether)
        self.assertEqual(placed.path(), "etc/aether/Report.txt")
        self.assertEqual(placed.depth(), 2)

    def test_a_name_is_unique_in_a_folder_and_at_the_root(self):
        etc = self.folder("etc")
        self.folder("a", etc)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.folder("a", etc)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.folder("etc")                                                       # корень тома
        self.folder("etc", volume=self.other)                                         # в другом томе можно

    def test_an_object_needs_an_item_and_a_folder_must_not_have_one(self):
        with self.assertRaises(ValidationError):
            Placement(volume=self.volume, kind="item", name="x").full_clean()
        with self.assertRaises(ValidationError):
            Placement(volume=self.volume, kind="folder", name="x", item=self.item).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Placement.objects.create(volume=self.volume, kind="item", name="x")

    def test_a_parent_must_be_a_folder_of_the_same_volume(self):
        placed = Placement.objects.create(volume=self.volume, kind="item", item=self.item)
        with self.assertRaises(ValidationError):
            Placement(volume=self.volume, kind="folder", name="x", parent=placed).full_clean()
        elsewhere = self.folder("e", volume=self.other)
        with self.assertRaises(ValidationError):
            Placement(volume=self.volume, kind="folder", name="x", parent=elsewhere).full_clean()

    def test_folders_nest_up_to_the_limit(self):
        node = None
        for index in range(MAX_DEPTH):
            node = self.folder(f"d{index}", node)
        with self.assertRaises(ValidationError):
            Placement(volume=self.volume, kind="folder", name="deeper", parent=node).full_clean()

    def test_a_folder_cannot_become_its_own_ancestor(self):
        a = self.folder("a")
        b = self.folder("b", a)
        a.parent = b
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_a_replacing_mode_needs_text_and_the_none_mode_needs_nothing(self):
        with self.assertRaises(ValidationError):
            Placement(volume=self.volume, kind="item", item=self.item, access_mode="replace").full_clean()
        with self.assertRaises(ValidationError):
            Placement(volume=self.volume, kind="item", item=self.item, state_mode="replace").full_clean()
        Placement(volume=self.volume, kind="item", item=self.item, access_mode="none", state_mode="none").full_clean()
        Placement(volume=self.volume, kind="item", item=self.item, access_mode="replace", access="alpha").full_clean()

    def test_a_whiteout_is_a_row_with_a_name_and_no_object(self):
        row = Placement(volume=self.volume, kind="whiteout", name="passwd")
        row.full_clean()
        row.save()
        self.assertIsNone(row.item_id)


class PlayerLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_format("txt", ".txt", "text_asset")
        cls.user = get_user_model().objects.create_user("ivan", password="x")
        cls.machine = Machine.objects.create(name="A", hostname="a")
        cls.volume = Volume.objects.create(slug="v")
        cls.instance = VolumeInstance.objects.create(volume=cls.volume, host=cls.machine)
        cls.item = Item.objects.create(slug="n", name="n", format="txt", body="x")

    def test_an_instance_is_unique_per_host_and_unique_when_external(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            VolumeInstance.objects.create(volume=self.volume, host=self.machine)
        VolumeInstance.objects.create(volume=self.volume, host=None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            VolumeInstance.objects.create(volume=self.volume, host=None)

    def test_a_path_is_normalized_and_unique_for_a_player_and_an_instance(self):
        row = PlayerFile.objects.create(user=self.user, instance=self.instance, path="/etc//hosts/", item=self.item)
        self.assertEqual(row.path, "etc/hosts")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlayerFile.objects.create(user=self.user, instance=self.instance, path="etc/hosts")

    def test_the_same_path_in_another_players_layer_is_another_row(self):
        other = get_user_model().objects.create_user("petr", password="x")
        PlayerFile.objects.create(user=self.user, instance=self.instance, path="a")
        PlayerFile.objects.create(user=other, instance=self.instance, path="a")

    def test_a_row_has_an_object_or_its_own_bytes_but_not_both(self):
        PlayerFile.objects.create(user=self.user, instance=self.instance, path="slice.bin", data=b"\x00\x01")
        PlayerFile.objects.create(user=self.user, instance=self.instance, path="sig.txt", content="-----BEGIN-----")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlayerFile.objects.create(user=self.user, instance=self.instance, path="bad", item=self.item, data=b"x")

    def test_an_edited_text_keeps_its_object(self):
        row = PlayerFile.objects.create(user=self.user, instance=self.instance, path="n.txt", item=self.item, content="mine")
        self.assertEqual((row.item_id, row.content), (self.item.pk, "mine"))

    def test_deleting_an_object_removes_the_rows_that_pointed_at_it(self):
        PlayerFile.objects.create(user=self.user, instance=self.instance, path="n", item=self.item)
        Item.objects.filter(pk=self.item.pk).delete()
        self.assertFalse(PlayerFile.objects.exists())
