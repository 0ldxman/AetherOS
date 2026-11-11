"""Картинка и узор рабочего стола ОС: значения, слои на странице, отдача файла."""
import json
from unittest import mock
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from assets.nextcloud import NextcloudFile
from machines.models import Machine, SystemType
from machines.world import wallpaper
from team.testing import full_role


class ValuesTests(TestCase):
    def test_defaults_fill_the_gaps_and_extra_keys_are_dropped(self):
        self.assertEqual(wallpaper.clean({"mode": "cover", "junk": 1})["mode"], "cover")
        self.assertNotIn("junk", wallpaper.clean({"junk": 1}))
        self.assertEqual(wallpaper.clean(None), wallpaper.DEFAULT)
        self.assertEqual(wallpaper.problems({}), [])
        self.assertTrue(wallpaper.is_empty({}))

    def test_bad_values_are_named(self):
        for bad in ({"mode": "tile"}, {"pattern": "stars"}, {"pattern_color": "red"}, {"opacity": 101}, {"opacity": -1}, {"pattern_size": 3},
                    {"pattern_size": 1000}, {"pattern_opacity": "x"}, {"opacity": True}, {"file_id": "../etc"}):
            self.assertTrue(wallpaper.problems(bad), bad)

    def test_the_system_model_rejects_bad_values(self):
        system = SystemType(code="X", name="X", wallpaper={"pattern": "stars"})
        with self.assertRaises(ValidationError):
            system.full_clean()

    def test_layers_follow_the_settings(self):
        self.assertEqual(wallpaper.render("/u", {}), "")
        html = wallpaper.render("/desktop/wallpaper/X/?v=7", {"file_id": "7", "mode": "center", "opacity": 80})
        self.assertIn('id="os-wallpaper"', html)
        self.assertIn("object-fit:scale-down", html)
        self.assertIn("opacity:0.8", html)
        self.assertNotIn('id="os-pattern"', html)
        cover = wallpaper.render("/u", {"file_id": "7", "mode": "cover"})
        self.assertIn("object-fit:cover", cover)
        pattern = wallpaper.render("/u", {"pattern": "dots", "pattern_color": "#ff0000", "pattern_size": 30, "pattern_opacity": 20})
        self.assertNotIn("<img", pattern)
        self.assertIn('id="os-pattern"', pattern)
        self.assertIn("30px 30px", pattern)
        self.assertIn("%23ff0000", pattern)
        for kind in ("grid", "dots", "plus"):
            self.assertIn("svg", unquote(wallpaper.tile(kind, "#ffffff", 24)))
        self.assertEqual(wallpaper.render("/u", {"pattern": "grid", "pattern_color": "red; x"}), "")      # невалидное не попадает в страницу


class LikeTheStyleTests(TestCase):
    def test_the_default_pattern_repeats_the_grid_of_the_style(self):
        self.assertEqual((wallpaper.DEFAULT["pattern_size"], wallpaper.DEFAULT["pattern_color"], wallpaper.DEFAULT["pattern_opacity"]), (0, "", 100))
        self.assertEqual(wallpaper.problems({"pattern": "grid"}), [])
        aether = wallpaper.style_look("aether", {})
        self.assertEqual(aether, {"size": 48, "color": "#212121"})
        self.assertEqual(wallpaper.style_look("modern", {})["color"], "#20252e")
        self.assertEqual(wallpaper.style_look("aether", {"--cell": "32px", "--line-faint": "#112233"}), {"size": 32, "color": "#112233"})
        self.assertEqual(wallpaper.style_look("aether", {"--cell": "2rem", "--line-faint": "rgb(1, 2, 3)"}), aether)      # что не разобрать, по умолчанию
        html = wallpaper.render("/u", {"pattern": "grid"}, {"size": 32, "color": "#112233"})
        self.assertIn("32px 32px", html)
        self.assertIn("%23112233", html)
        self.assertIn("opacity:1", html)
        own = wallpaper.render("/u", {"pattern": "grid", "pattern_size": 20, "pattern_color": "#ff0000"}, {"size": 32, "color": "#112233"})
        self.assertIn("20px 20px", own)
        self.assertIn("%23ff0000", own)

    def test_old_defaults_become_like_the_style(self):
        import importlib

        from django.apps import apps

        system = SystemType.objects.get(code="AETHER")
        system.wallpaper = {"pattern": "grid", "pattern_size": 24, "pattern_color": "#ffffff", "pattern_opacity": 15}
        system.save()
        other = SystemType.objects.create(code="OTHER", name="Other", wallpaper={"pattern": "dots", "pattern_size": 30, "pattern_color": "#ffffff", "pattern_opacity": 15})
        importlib.import_module("machines.migrations.0038_wallpaper_pattern_like_style").like_style(apps, None)
        system.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((system.wallpaper["pattern_size"], system.wallpaper["pattern_color"], system.wallpaper["pattern_opacity"]), (0, "", 100))
        self.assertEqual(other.wallpaper["pattern_size"], 30)          # свои значения не трогаются


@override_settings(FORCE_SCRIPT_NAME=None)
class PageTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        Machine.objects.create(name="Main", hostname="aether-main")
        self.system = SystemType.objects.get(code="AETHER")
        self.system.wallpaper = {"file_id": "42", "file_name": "logo.png", "mode": "center", "opacity": 70, "pattern": "grid"}
        self.system.save()
        self.staff = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())

    def test_the_desktop_of_the_system_carries_the_layers(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse("studio_style_preview", kwargs={"code": "AETHER"}), {"preview_os": "AETHER", "preview_style": "aether"}).content.decode()
        self.assertIn('id="os-wallpaper"', html)
        self.assertIn(reverse("os_wallpaper", kwargs={"code": "AETHER"}) + "?v=42", html)
        self.assertIn('id="os-pattern"', html)
        self.assertIn("?v=42&amp;file=42", html)          # сотрудник просит файл и до сохранения
        self.assertIn("background-image:none", html)   # рисунок фона стиля снят

    def test_the_preview_shows_unsaved_values_and_drops_invalid_ones(self):
        self.client.force_login(self.staff)
        url = reverse("studio_style_preview", kwargs={"code": "AETHER"})
        query = {"preview_os": "AETHER", "preview_style": "aether", "preview_wall": json.dumps({"file_id": "", "pattern": "plus"})}
        html = self.client.get(url, query).content.decode()
        self.assertNotIn('id="os-wallpaper"', html)
        self.assertIn('id="os-pattern"', html)
        html = self.client.get(url, {**query, "preview_wall": json.dumps({"pattern": "stars"})}).content.decode()
        self.assertIn('id="os-wallpaper"', html)          # невалидное отбрасывается: остаётся сохранённое

    def test_the_file_is_served_without_keys_but_only_the_chosen_one(self):
        url = reverse("os_wallpaper", kwargs={"code": "AETHER"})
        with mock.patch("assets.views._serve_asset_file", return_value=HttpResponse(b"png")) as serve:
            response = self.client.get(url)
            self.assertEqual((response.status_code, serve.call_args.args[1].file_id), (200, "42"))
            self.assertIn("max-age", response["Cache-Control"])
            self.client.get(url, {"file": "99"})                           # чужой id от игрока не принимается
            self.assertEqual(serve.call_args.args[1].file_id, "42")
            self.client.force_login(self.staff)
            self.client.get(url, {"file": "99"})                           # сотрудник смотрит несохранённый
            self.assertEqual(serve.call_args.args[1].file_id, "99")
        self.system.wallpaper = {}
        self.system.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("os_wallpaper", kwargs={"code": "NOPE"})).status_code, 404)

    def test_stored_file_name_checks_the_storage(self):
        client = mock.Mock()
        with mock.patch("assets.nextcloud.NextcloudClient.from_settings", return_value=client):
            client.get_file_by_id.return_value = NextcloudFile(file_id="1", path="AETHER/a.png", filename="a.png", is_directory=False)
            self.assertEqual(wallpaper.stored_file_name("1"), "a.png")
            client.get_file_by_id.return_value = NextcloudFile(file_id="1", path="AETHER/a.txt", filename="a.txt", is_directory=False)
            with self.assertRaises(ValidationError):
                wallpaper.stored_file_name("1")
            client.get_file_by_id.return_value = None
            with self.assertRaises(ValidationError):
                wallpaper.stored_file_name("1")
