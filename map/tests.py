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
