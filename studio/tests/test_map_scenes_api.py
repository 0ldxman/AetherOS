"""Сцены карты в Студии: список, правка с проверкой пометок, снимки и откат, копия, выгрузка и загрузка.

Запуск: python manage.py test studio.tests.test_map_scenes_api
"""
from team.testing import full_role
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from map.models import MapScene

API = "/studio/api/map/scenes"
MARKER = {"type": "marker", "coords": [10, 20], "label": "Порт", "color": "red"}


@override_settings(FORCE_SCRIPT_NAME=None)
class MapScenesApiTests(TestCase):
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
        response = getattr(self.client, method)(f"{API}{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def make(self, **extra):
        return self.call("post", "", {"slug": "port", "title": "Порт", "features": [MARKER], **extra})

    def test_create_list_read_and_the_features_are_normalized(self):
        status, scene = self.make(base_date="2041-03-12", keys="key_a and key_b")
        self.assertEqual((status, scene["features"][0]["type"], scene["keys"]), (200, "marker", "key_a and key_b"))
        row = self.call("get", "?q=port")[1][0]
        self.assertEqual((row["features"], row["keys"], row["base_date"]), (1, True, "2041-03-12"))
        self.assertEqual(self.call("get", f"/{scene['id']}")[1]["slug"], "port")

    def test_the_key_of_a_feature_goes_in_and_out_as_text(self):
        scene = self.make(features=[{**MARKER, "key": "key_a and not key_b"}, {**MARKER, "key": "single"}])[1]
        self.assertEqual([f["key"] for f in scene["features"]], ["key_a and not key_b", "single"])
        self.assertEqual([f["key"] for f in self.call("get", f"/{scene['id']}")[1]["features"]], ["key_a and not key_b", "single"])
        self.assertEqual(self.make(slug="x2", features=[{**MARKER, "key": "a and"}])[0], 400)

    def test_bad_data_is_refused(self):
        self.assertEqual(self.make(features=[{"type": "marker", "coords": [999, 20]}])[0], 400)
        self.assertEqual(self.make(features=[{"type": "nope"}])[0], 400)
        self.assertEqual(self.make(bounds=[10, 0, 5, 5])[0], 400)
        self.assertEqual(self.make(keys="a and")[0], 400)
        self.assertEqual(self.make(slug="bad slug")[0], 400)
        self.assertEqual(MapScene.objects.count(), 0)

    def test_every_save_leaves_a_snapshot_and_restore_brings_it_back(self):
        scene = self.make()[1]
        edited = {**scene, "title": "Новый порт", "features": [MARKER, {**MARKER, "coords": [11, 21]}]}
        self.call("put", f"/{scene['id']}", edited)
        revisions = self.call("get", f"/{scene['id']}/revisions")[1]
        self.assertEqual([(r["title"], r["features"]) for r in revisions], [("Новый порт", 2), ("Порт", 1)])
        self.assertEqual(revisions[0]["saved_by"], "boss")
        restored = self.call("post", f"/{scene['id']}/revisions/{revisions[1]['id']}/restore")[1]
        self.assertEqual((restored["title"], len(restored["features"])), ("Порт", 1))

    def test_copy_gets_a_free_slug(self):
        scene = self.make()[1]
        first = self.call("post", f"/{scene['id']}/copy")[1]
        second = self.call("post", f"/{scene['id']}/copy")[1]
        self.assertEqual((first["slug"], second["slug"]), ("port-copy", "port-copy-2"))

    def test_export_and_import_round_trip(self):
        scene = self.make()[1]
        out = self.call("get", f"/export?ids={scene['id']}")[1]
        self.assertEqual([i["slug"] for i in out["items"]], ["port"])
        self.call("delete", f"/{scene['id']}")
        self.assertEqual(self.call("post", "/import", out)[1], {"created": 1, "updated": 0})
        self.assertEqual(self.call("post", "/import", {"items": [{"title": "no slug"}]})[0], 400)

    def test_options_and_region_resolve(self):
        from map.models import Country, Ownership, Province

        options = self.call("get", "/options")[1]
        self.assertEqual((options["colors"][0], options["icons"][0]["name"], options["max_features"]), ("red", "pin", 400))
        country = Country.objects.create(code="AAA", name="Alpha", valid_from="1900-01-01")
        province = Province.objects.create(code="AAA-1", source_code="s1", name="One")
        Ownership.objects.create(province=province, country=country, date_from="1950-01-01", de_facto=True)
        out = self.call("post", "/resolve", {"tokens": ["AAA-1", "AAA", "nope"], "date": "1960-01-01"})[1]
        self.assertEqual(sorted((g["kind"], g["codes"]) for g in out["groups"]), [("country", ["s1"]), ("province", ["s1"])])
        self.assertEqual(out["unknown"], ["nope"])
