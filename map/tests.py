from django.test import TestCase

from .models import MapScene

# Create your tests here.



class MapSceneTests(TestCase):
    def test_features_are_validated_and_normalized(self):
        from django.core.exceptions import ValidationError

        from .scenes import clean_features

        clean = clean_features([
            {"type": "marker", "coords": [19.94, 50.06], "label": "Краков", "color": "red", "junk": 1},
            {"type": "arrow", "coords": [[0, 0], [10, 10]], "width": 99, "dash": True},
            {"type": "circle", "coords": [1, 2], "radius_km": 50},
            {"type": "text", "coords": [1, 2], "text": "Штаб"},
            {"type": "region", "token": "POL", "color": "blue"},
        ])
        self.assertEqual(clean[0], {"type": "marker", "coords": [19.94, 50.06], "label": "Краков", "color": "red"})
        self.assertEqual(clean[1]["width"], 8)
        for bad in (
            [{"type": "blob"}],
            [{"type": "marker", "coords": [200, 0]}],
            [{"type": "line", "coords": [[0, 0]]}],
            [{"type": "polygon", "coords": [[0, 0], [1, 1]]}],
            [{"type": "circle", "coords": [0, 0], "radius_km": 0}],
            [{"type": "marker", "coords": [0, 0], "color": "pink"}],
            [{"type": "region", "token": "-CZE-3"}],
            [{"type": "marker", "coords": [0, 0], "key": {"all": []}}],
            "not a list",
        ):
            with self.assertRaises(ValidationError, msg=bad):
                clean_features(bad)

    def test_features_can_be_limited_in_time(self):
        from datetime import date

        from django.core.exceptions import ValidationError

        from .scenes import clean_features, visible_features

        features = clean_features([
            {"type": "marker", "coords": [0, 0], "label": "всегда"},
            {"type": "marker", "coords": [1, 1], "label": "до", "to": "2041-03-12"},
            {"type": "marker", "coords": [2, 2], "label": "после", "from": "2041-03-13"},
            {"type": "marker", "coords": [3, 3], "label": "промежуток", "from": "2041-01-01", "to": "2041-12-31"},
        ])
        labels = lambda on: [f["label"] for f in visible_features(features, set(), on)]
        self.assertEqual(labels(None), ["всегда", "до", "после", "промежуток"])      # без даты видно всё
        self.assertEqual(labels(date(2041, 3, 12)), ["всегда", "до", "промежуток"])
        self.assertEqual(labels(date(2041, 3, 13)), ["всегда", "после", "промежуток"])
        self.assertEqual(labels(date(2042, 1, 1)), ["всегда", "после"])
        self.assertNotIn("from", visible_features(features, set(), date(2041, 3, 13))[1])
        for bad in ({"from": "вчера"}, {"from": "2041-05-01", "to": "2041-01-01"}):
            with self.assertRaises(ValidationError):
                clean_features([{"type": "marker", "coords": [0, 0], **bad}])

    def test_visible_features_follow_keys_and_hide_the_key_field(self):
        from .scenes import visible_features

        features = [
            {"type": "marker", "coords": [0, 0]},
            {"type": "marker", "coords": [1, 1], "key": "secret"},
        ]
        self.assertEqual(len(visible_features(features, set())), 1)
        shown = visible_features(features, {"secret"})
        self.assertEqual(len(shown), 2)
        self.assertNotIn("key", shown[1])

    def test_internal_url_accepts_site_and_wiki_paths_only(self):
        from .scenes import internal_url

        self.assertTrue(internal_url("/apps/wiki/x").endswith("/apps/wiki/x"))
        self.assertIn("Technologies", internal_url("Technologies/Report"))
        for bad in ("", "http://evil.example", "//evil.example", "javascript:alert(1)", "a\\b"):
            self.assertEqual(internal_url(bad), "", bad)

    def test_scene_clean_checks_bounds_and_zoom(self):
        from django.core.exceptions import ValidationError

        scene = MapScene(slug="s", title="S", bounds=[10, 10, 5, 20])
        with self.assertRaises(ValidationError):
            scene.full_clean()
        scene = MapScene(slug="s", title="S", min_zoom=5, max_zoom=3)
        with self.assertRaises(ValidationError):
            scene.full_clean()
        MapScene(slug="s", title="S", bounds=[5, 10, 10, 20], features=[{"type": "marker", "coords": [1, 2]}]).full_clean()


# форма истории сохранений идёт в каждом сохранении через админку
REVISIONS_FORM = {"revisions-TOTAL_FORMS": 0, "revisions-INITIAL_FORMS": 0,
                  "revisions-MIN_NUM_FORMS": 0, "revisions-MAX_NUM_FORMS": 0}


class MapSceneAdminTests(TestCase):
    def test_editor_page_renders_for_staff_and_keys_accept_expressions(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        from .scenes import clean_features

        from secure.models import Key

        Key.objects.create(slug="secret_key")
        user = get_user_model().objects.create_superuser("boss", password="pw")
        self.client.force_login(user)
        response = self.client.get(reverse("admin:map_mapscene_add"))
        self.assertContains(response, 'value="secret_key"')
        self.assertContains(response, 'id="se-frame"')
        self.assertContains(response, "scene_edit")
        self.assertContains(response, 'value="red"')
        for control in ('id="se-undo"', 'id="se-layers"', 'id="se-theme"', 'id="se-viewer"', 'id="se-duplicate"'):
            self.assertContains(response, control)

        cleaned = clean_features([{"type": "marker", "coords": [0, 0], "key": "a and not b"}])
        self.assertEqual(cleaned[0]["key"], {"all": ["a", {"not": "b"}]})
        self.assertEqual(clean_features([{"type": "marker", "coords": [0, 0], "key": "  "}])[0].get("key"), None)

    def test_saving_a_scene_through_the_admin(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        import json

        user = get_user_model().objects.create_superuser("boss", password="pw")
        self.client.force_login(user)
        response = self.client.post(reverse("admin:map_mapscene_add"), {
            "title": "Рейд", "slug": "raid", "mode": "political", "lat": 50, "lon": 19, "zoom": 5,
            "features": json.dumps([{"type": "marker", "coords": [19, 50], "label": "A", "key": "secret"}]),
            **REVISIONS_FORM,
        })
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        scene = MapScene.objects.get(slug="raid")
        self.assertEqual(scene.features[0]["key"], "secret")


class MapEditorAccessTests(TestCase):
    def test_staff_open_the_map_without_a_machine_others_do_not(self):
        from django.contrib.auth import get_user_model

        url = "/apps/map/?embed=1&scene_edit=1"
        staff = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 403)


class ProvinceLinkTests(TestCase):
    def test_link_prefers_the_province_then_the_country_and_rejects_unsafe(self):
        from .views import link_of

        self.assertEqual(link_of("https://wiki.example/p", "https://wiki.example/c"), "https://wiki.example/p")
        self.assertEqual(link_of("", "/wiki/Poland"), "/wiki/Poland")
        self.assertEqual(link_of("javascript:alert(1)", "//evil.example"), "")
        self.assertEqual(link_of("", ""), "")


class RegionLookupTests(TestCase):
    def test_lookup_finds_provinces_and_countries_for_staff_only(self):
        from datetime import date

        from django.contrib.auth import get_user_model
        from django.urls import reverse

        from .bounds import lookup_regions
        from .models import Country, Province

        Country.objects.create(code="POL-2013", name="Польша", valid_from=date(2013, 1, 1))
        Province.objects.create(code="POL-2", source_code="POL-3170", name="Малая Польша")
        Province.objects.create(code="DEU-1", source_code="DEU-1", name="Бавария")

        found = lookup_regions("Польш")
        kinds = {(r["kind"], r["token"]) for r in found}
        self.assertEqual(kinds, {("country", "POL"), ("province", "POL-2")})
        province = next(r for r in found if r["kind"] == "province")
        self.assertEqual(len(province["bounds"]), 4)               # рамка из province_bounds.json
        self.assertEqual(lookup_regions("п"), [])                  # слишком короткий запрос
        self.assertEqual([r["token"] for r in lookup_regions("DEU-1")], ["DEU-1"])

        url = reverse("admin:map_mapscene_lookup") + "?q=%D0%9F%D0%BE%D0%BB%D1%8C%D1%88"
        self.assertEqual(self.client.get(url).status_code, 302)    # без входа в админку
        staff = get_user_model().objects.create_superuser("boss", password="pw")
        self.client.force_login(staff)
        data = self.client.get(url).json()
        self.assertEqual({r["token"] for r in data["results"]}, {"POL", "POL-2"})


class SceneApiTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.open = MapScene.objects.create(slug="open", title="Открытая", lat=50, lon=19, zoom=5, flat=True,
            bounds=[10, 40, 30, 60], base_date="2041-03-12",
            features=[{"type": "marker", "coords": [19, 50], "label": "А"},
                      {"type": "marker", "coords": [1, 1], "label": "Секрет", "key": "secret"},
                      {"type": "marker", "coords": [2, 2], "label": "Старое", "to": "2030-01-01"}])
        self.closed = MapScene.objects.create(slug="closed", title="Закрытая", key_condition="secret")
        self.staff = get_user_model().objects.create_user("boss", password="pw", is_staff=True)

    def test_list_and_detail_hide_what_the_player_has_no_key_for(self):
        self.client.force_login(self.staff)
        listing = self.client.get("/apps/map/api/scenes/").json()
        self.assertEqual([s["slug"] for s in listing], ["open"])

        data = self.client.get("/apps/map/api/scenes/open/").json()
        self.assertEqual((data["lat"], data["flat"], data["bounds"], data["date"]), (50, True, [10, 40, 30, 60], "2041-03-12"))
        self.assertEqual([f["label"] for f in data["features"]], ["А"])         # секретная и устаревшая отсеяны
        self.assertEqual(self.client.get("/apps/map/api/scenes/closed/").status_code, 404)
        self.assertEqual(self.client.get("/apps/map/api/scenes/nope/").status_code, 404)

    def test_the_date_can_be_overridden(self):
        self.client.force_login(self.staff)
        data = self.client.get("/apps/map/api/scenes/open/?date=2029-01-01").json()
        self.assertEqual([f["label"] for f in data["features"]], ["А", "Старое"])
        self.assertEqual(self.client.get("/apps/map/api/scenes/open/?date=bad").status_code, 400)


class SceneHistoryTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.boss = get_user_model().objects.create_superuser("boss", password="pw")
        self.client.force_login(self.boss)

    def _post_scene(self, **extra):
        import json

        from django.urls import reverse

        data = {"title": "Рейд", "slug": "raid", "mode": "political", "lat": 50, "lon": 19, "zoom": 5,
                "features": json.dumps([{"type": "marker", "coords": [19, 50], "label": "A"}]), **REVISIONS_FORM, **extra}
        return self.client.post(reverse("admin:map_mapscene_add"), data)

    def test_every_change_leaves_a_snapshot_and_can_be_restored(self):
        import json

        from django.urls import reverse

        self._post_scene()
        scene = MapScene.objects.get(slug="raid")
        self.assertEqual(scene.revisions.count(), 1)
        page = self.client.get(reverse("admin:map_mapscene_change", args=[scene.pk]))
        self.assertContains(page, "_saveasnew")             # «Сохранить как новый»
        self.assertContains(page, "История сохранений")
        self.client.post(reverse("admin:map_mapscene_change", args=[scene.pk]), {
            "title": "Рейд 2", "slug": "raid", "mode": "political", "lat": 51, "lon": 19, "zoom": 5,
            "features": json.dumps([]), **REVISIONS_FORM,
        })
        scene.refresh_from_db()
        self.assertEqual((scene.title, scene.features), ("Рейд 2", []))
        first = scene.revisions.last()
        page = self.client.get(reverse("admin:map_mapscene_revert", args=[scene.pk, first.pk]))
        self.assertContains(page, "Восстановить")
        self.client.post(reverse("admin:map_mapscene_revert", args=[scene.pk, first.pk]))
        scene.refresh_from_db()
        self.assertEqual((scene.title, len(scene.features)), ("Рейд", 1))
        self.assertEqual(scene.revisions.count(), 3)        # откат тоже в истории

    def test_save_as_new_makes_a_copy(self):
        import json

        from django.urls import reverse

        self._post_scene()
        scene = MapScene.objects.get(slug="raid")
        self.client.post(reverse("admin:map_mapscene_change", args=[scene.pk]), {
            "_saveasnew": "1", "title": "Копия", "slug": "raid-copy", "mode": "political", "lat": 50, "lon": 19,
            "zoom": 5, "features": json.dumps([{"type": "marker", "coords": [19, 50], "label": "A"}]),
            **REVISIONS_FORM,
        })
        self.assertTrue(MapScene.objects.filter(slug="raid-copy").exists())
        self.assertTrue(MapScene.objects.filter(slug="raid").exists())

    def test_export_and_import_round_trip(self):
        import json

        from django.urls import reverse

        from .revisions import export_scenes, import_scenes

        scene = MapScene.objects.create(slug="a", title="A", base_date="2041-03-12", flat=True,
                                        features=[{"type": "marker", "coords": [1, 2]}])
        dump = json.loads(json.dumps(export_scenes([scene])))
        scene.delete()
        self.assertEqual(import_scenes(dump), (1, 0))
        again = MapScene.objects.get(slug="a")
        self.assertEqual((again.flat, str(again.base_date), len(again.features)), (True, "2041-03-12", 1))
        self.assertEqual(import_scenes(dump), (0, 1))

        # плохая сцена отменяет весь файл
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            import_scenes([{"slug": "b", "title": "B"}, {"slug": "c", "title": "C", "features": [{"type": "blob"}]}])
        self.assertFalse(MapScene.objects.filter(slug="b").exists())

        # действие админки и страница загрузки
        response = self.client.post(reverse("admin:map_mapscene_changelist"),
                                    {"action": "export_json", "_selected_action": [again.pk]})
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(response.content)[0]["slug"], "a")
        page = self.client.get(reverse("admin:map_mapscene_import"))
        self.assertContains(page, "Загрузить")
        self.client.post(reverse("admin:map_mapscene_import"), {"text": json.dumps([{"slug": "z", "title": "Z"}])})
        self.assertTrue(MapScene.objects.filter(slug="z").exists())


class SceneFindTests(TestCase):
    def test_find_lists_scenes_for_the_wiki_editor(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        MapScene.objects.create(slug="raid", title="Операция Висла")
        MapScene.objects.create(slug="other", title="Другая")
        self.client.force_login(get_user_model().objects.create_superuser("boss", password="pw"))
        url = reverse("admin:map_mapscene_find")
        self.assertEqual({i["slug"] for i in self.client.get(url).json()["items"]}, {"raid", "other"})
        self.assertEqual([i["slug"] for i in self.client.get(url + "?q=raid").json()["items"]], ["raid"])
