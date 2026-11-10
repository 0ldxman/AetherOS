"""Список объектов: несколько признаков сразу, тип «архив» и «ключ», число архивов у карточки.

Запуск: python manage.py test studio.tests.test_library
"""
from team.testing import full_role
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.models import KEY_FORMAT, FileFormat, Item, ItemMember, Placement, Volume


@override_settings(FORCE_SCRIPT_NAME=None)
class LibraryFilterTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())
        self.client.force_login(self.boss)
        FileFormat.objects.get_or_create(name="txt", defaults={"extension": ".txt"})
        self.volume = Volume.objects.create(slug="v")
        self.lost = Item.objects.create(slug="lost", name="lost", format="txt", body="x")
        self.layered = Item.objects.create(slug="layered", name="layered", format="txt", body="x", state="> mask")
        self.layered_lost = Item.objects.create(slug="both", name="both", format="txt", body="x", state="> mask")
        self.packed = Item.objects.create(slug="packed", name="packed", format="txt", body="x")
        self.archive = Item.objects.create(slug="pack", name="pack.zip", format="txt")
        Placement.objects.create(volume=self.volume, kind="item", item=self.layered, name="layered")
        Placement.objects.create(volume=self.volume, kind="item", item=self.archive, name="pack.zip")
        ItemMember.objects.create(archive=self.archive, item=self.packed, path="a.txt")

    def rows(self, query=""):
        return {r["slug"]: r for r in self.client.get(f"/studio/api/items{query}").json()}

    def test_several_flags_must_all_hold(self):
        self.assertEqual(set(self.rows("?only=orphans")), {"lost", "both"})
        self.assertEqual(set(self.rows("?only=layers")), {"layered", "both"})
        self.assertEqual(set(self.rows("?only=orphans,layers")), {"both"})
        self.assertEqual(set(self.rows("?only=orphans,layers,mine")), set())

    def test_an_object_that_is_only_in_an_archive_is_not_an_orphan(self):
        self.assertNotIn("packed", self.rows("?only=orphans"))
        self.assertEqual(self.rows()["packed"]["archives"], 1)

    def test_the_kind_archive_and_key(self):
        rows = self.rows()
        self.assertEqual((rows["pack"]["kind"], rows["lost"]["kind"]), ("archive", "text"))
        self.assertEqual(set(self.rows("?kind=archive")), {"pack"})
        key = Item.objects.create(slug="alpha", name="Alpha key", format=KEY_FORMAT)
        self.assertEqual(self.rows()["alpha"]["kind"], "key")
        self.assertEqual(set(self.rows("?kind=key")), {"alpha"})

    def test_the_card_knows_in_how_many_archives_it_lies(self):
        card = self.client.get(f"/studio/api/items/{self.packed.pk}").json()
        self.assertEqual((card["in_archives"], len(card["placements"])), (1, 0))
