"""Предпросмотр стиля в студии: страница стола и страница-образец принимают несохранённые стиль и токены только от сотрудника."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from machines.models import Machine, SystemType


@override_settings(FORCE_SCRIPT_NAME=None)
class StylePreviewTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        Machine.objects.create(name="Main", hostname="aether-main")
        self.staff = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        self.query = {"preview_os": "AETHER", "preview_style": "modern", "preview_tokens": json.dumps({"--accent": "#e0709a"})}

    def test_the_desktop_preview_shows_the_unsaved_style_and_tokens(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse("studio_style_preview", kwargs={"code": "AETHER"}), self.query).content.decode()
        self.assertIn('data-theme="modern"', html)
        self.assertIn("--accent: #e0709a", html)
        self.assertIn('data-preview="1"', html)
        self.assertIn(reverse("studio_preview_page", kwargs={"kind": "terminal"}), html)       # адрес терминала для консоли в стилях, которые её выделяют

    def test_invalid_tokens_are_dropped_and_unknown_styles_ignored(self):
        self.client.force_login(self.staff)
        url = reverse("studio_style_preview", kwargs={"code": "AETHER"})
        bad = {**self.query, "preview_tokens": json.dumps({"--accent": "red; x"})}
        self.assertNotIn("red; x", self.client.get(url, bad).content.decode())
        self.assertIn('data-theme="aether"', self.client.get(url, {**self.query, "preview_style": "nope"}).content.decode())

    def test_only_staff_can_open_the_preview(self):
        player = get_user_model().objects.create_user("ivan", password="pw")
        self.client.force_login(player)
        self.assertEqual(self.client.get(reverse("studio_style_preview", kwargs={"code": "AETHER"})).status_code, 302)
        self.assertEqual(self.client.get(reverse("studio_preview_page", kwargs={"kind": "wiki"})).status_code, 302)

    def test_the_sample_pages_render(self):
        self.client.force_login(self.staff)
        for kind in ("mail", "wiki", "terminal", "map", "files"):
            self.assertEqual(self.client.get(reverse("studio_preview_page", kwargs={"kind": kind}), self.query).status_code, 200, kind)
        self.assertTrue(SystemType.objects.filter(code="AETHER").exists())
