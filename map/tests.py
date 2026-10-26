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
